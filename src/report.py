"""Turn an analysis into a markdown incident report."""

from __future__ import annotations

from datetime import timedelta

from analysis import Analysis, error_key, group_by_request, root_cause_tally
from log_parser import LogEvent


def _change(finding) -> str:
    return "new" if finding.ratio is None else f"{finding.ratio:.1f}x"


def _example_trace(events: list[LogEvent], analysis: Analysis, finding) -> list[LogEvent]:
    for event in events:
        if (
            event.is_error
            and event.request_id
            and event.timestamp >= analysis.deploy_time
            and error_key(event) == (finding.service, finding.error_type)
        ):
            return group_by_request(events)[event.request_id]
    return []


def build_report(analysis: Analysis, events: list[LogEvent], malformed_count: int, log_name: str) -> str:
    lines = [
        f"# Incident report: release {analysis.release}",
        "",
        f"Log: `{log_name}`. Deploy at {analysis.deploy_time:%Y-%m-%d %H:%M:%S} UTC.",
        f"Compared the {analysis.window_minutes} minutes before the deploy with the "
        f"{analysis.window_minutes} minutes after.",
        f"An error type is flagged when it has at least {analysis.min_count} errors after the deploy and "
        f"is either new or at least {analysis.ratio_threshold:g}x its count before.",
        "",
        f"Errors in the window: {analysis.before_errors} before, {analysis.after_errors} after. "
        f"Malformed lines skipped: {malformed_count}.",
        "",
        "## Findings",
        "",
    ]

    if not analysis.findings:
        lines.append("No regressions found.")
        return "\n".join(lines) + "\n"

    lines += [
        "| Service | Error type | Before | After | Change |",
        "|---|---|---|---|---|",
    ]
    for f in analysis.findings:
        lines.append(f"| {f.service} | {f.error_type} | {f.before_count} | {f.after_count} | {_change(f)} |")

    lines += ["", "## Likely root cause", ""]
    for f in analysis.findings:
        tally = root_cause_tally(
            events, f.service, f.error_type,
            since=analysis.deploy_time,
            until=analysis.deploy_time + timedelta(minutes=analysis.window_minutes),
        )
        total = sum(tally.values())
        lines.append(f"{f.service} {f.error_type}: {total} affected requests.")
        for (service, error_type), count in tally.most_common():
            lines.append(f"- {count} of {total} ({count / total:.0%}) first failed in {service} with {error_type}.")
        lines.append("")

    trace = _example_trace(events, analysis, analysis.findings[0])
    if trace:
        lines += [f"## Example trace: {trace[0].request_id}", "", "```"]
        for e in trace:
            lines.append(f"{e.timestamp:%H:%M:%S} {e.level:<5} {e.service:<17} {e.message}")
        lines += ["```", ""]

    return "\n".join(lines)
