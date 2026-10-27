"""Find what broke after a release and which service failed first.

The checks work on ERROR events only:

* compare_before_after: count errors per (service, error type) in the window
  before a deploy and the same-length window after it. An error type is flagged
  when it has at least `min_count` errors after the deploy AND either did not
  occur before ("new") or grew by at least `ratio_threshold` times ("spike").
  The minimum count stops a jump from 1 error to 3 from raising an alarm.
* trace_request / root_cause: follow one request across services. The root
  cause is the first ERROR in the request's trace.
* root_cause_tally: for a flagged error type, count which error started each
  affected request. A downstream error that always starts after an upstream one
  points at the upstream service.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from log_parser import LogEvent

DEPLOY_SERVICE = "deploy-bot"


@dataclass(frozen=True)
class Finding:
    service: str
    error_type: str
    before_count: int
    after_count: int
    kind: str  # "spike" or "new"

    @property
    def ratio(self) -> float | None:
        return None if self.before_count == 0 else self.after_count / self.before_count


@dataclass
class Analysis:
    deploy_time: datetime
    release: str
    window_minutes: int
    ratio_threshold: float
    min_count: int
    before_errors: int
    after_errors: int
    findings: list[Finding] = field(default_factory=list)


def error_key(event: LogEvent) -> tuple[str, str]:
    return event.service, event.error_type or "unknown"


def count_errors_by_type(events: list[LogEvent]) -> Counter:
    return Counter(error_key(e) for e in events if e.is_error)


def find_deploys(events: list[LogEvent]) -> list[tuple[datetime, str]]:
    """Deploy markers are events from deploy-bot that carry a release=... field."""
    deploys = [
        (e.timestamp, e.release)
        for e in events
        if e.service == DEPLOY_SERVICE and e.release
    ]
    return sorted(deploys)


def compare_before_after(
    events: list[LogEvent],
    deploy_time: datetime,
    window_minutes: int = 15,
    ratio_threshold: float = 3.0,
    min_count: int = 10,
) -> tuple[list[Finding], int, int]:
    """Return (findings, total errors before, total errors after)."""
    window = timedelta(minutes=window_minutes)
    before_start, after_end = deploy_time - window, deploy_time + window

    before = [e for e in events if e.is_error and before_start <= e.timestamp < deploy_time]
    after = [e for e in events if e.is_error and deploy_time <= e.timestamp < after_end]
    before_counts = Counter(error_key(e) for e in before)
    after_counts = Counter(error_key(e) for e in after)

    findings = []
    for key, after_count in after_counts.items():
        if after_count < min_count:
            continue
        before_count = before_counts.get(key, 0)
        if before_count == 0:
            kind = "new"
        elif after_count / before_count >= ratio_threshold:
            kind = "spike"
        else:
            continue
        findings.append(Finding(key[0], key[1], before_count, after_count, kind))

    findings.sort(key=lambda f: (-f.after_count, f.service, f.error_type))
    return findings, len(before), len(after)


def analyze(
    events: list[LogEvent],
    release: str | None = None,
    window_minutes: int = 15,
    ratio_threshold: float = 3.0,
    min_count: int = 10,
) -> Analysis:
    """Analyze one deploy: the named release, or the latest one in the log."""
    deploys = find_deploys(events)
    if not deploys:
        raise ValueError("No deploy marker found in the log.")

    if release is None:
        deploy_time, release = deploys[-1]
    else:
        matches = [d for d in deploys if d[1] == release]
        if not matches:
            raise ValueError(f"No deploy marker for release '{release}'.")
        deploy_time = matches[0][0]

    findings, before, after = compare_before_after(
        events, deploy_time, window_minutes, ratio_threshold, min_count
    )
    return Analysis(deploy_time, release, window_minutes, ratio_threshold, min_count, before, after, findings)


def group_by_request(events: list[LogEvent]) -> dict[str, list[LogEvent]]:
    grouped: dict[str, list[LogEvent]] = {}
    for event in events:
        if event.request_id:
            grouped.setdefault(event.request_id, []).append(event)
    for trace in grouped.values():
        trace.sort(key=lambda e: e.timestamp)  # stable: ties keep file order
    return grouped


def trace_request(events: list[LogEvent], request_id: str) -> list[LogEvent]:
    return group_by_request(events).get(request_id, [])


def root_cause(trace: list[LogEvent]) -> LogEvent | None:
    """The first ERROR in a request's trace, or None if the request had no error."""
    return next((e for e in trace if e.is_error), None)


def root_cause_tally(
    events: list[LogEvent],
    service: str,
    error_type: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Counter:
    """For requests that hit (service, error_type), count which error came first.

    Only errors from `since` (inclusive) to `until` (exclusive) make a request count as affected.
    """
    tally: Counter = Counter()
    for trace in group_by_request(events).values():
        hit = any(
            e.is_error
            and error_key(e) == (service, error_type)
            and (since is None or e.timestamp >= since)
            and (until is None or e.timestamp < until)
            for e in trace
        )
        if hit:
            first = root_cause(trace)
            tally[error_key(first)] += 1
    return tally
