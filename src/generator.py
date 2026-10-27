"""Generate synthetic application logs from a seed.

Same seed, same log. The log simulates a checkout flow: checkout-service calls
payment-service. Baseline error rates are small. With incident=True, the
payment-service timeout rate is multiplied after the deploy marker, and every
payment timeout makes checkout-service log an UpstreamFailure a second later,
so a downstream service reports errors for an upstream problem.

These logs are made up for this project. They are not from a real system.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

BASE_TIMEOUT_RATE = 0.01
VALIDATION_ERROR_RATE = 0.02
DEFAULT_START = datetime(2026, 3, 2, 14, 0, 0, tzinfo=timezone.utc)


def _line(ts: datetime, level: str, service: str, msg: str, request_id=None, error_type=None, release=None) -> str:
    parts = [f"{ts:%Y-%m-%dT%H:%M:%SZ}", level, service]
    if request_id:
        parts.append(f"request_id={request_id}")
    if error_type:
        parts.append(f"error_type={error_type}")
    if release:
        parts.append(f"release={release}")
    parts.append(f'msg="{msg}"')
    return " ".join(parts)


def generate_logs(
    seed: int = 1,
    start: datetime = DEFAULT_START,
    minutes: int = 40,
    deploy_minute: int = 20,
    incident: bool = True,
    multiplier: float = 10.0,
    requests_per_minute: int = 15,
    release: str = "v2.3.1",
) -> list[str]:
    rng = random.Random(seed)
    deploy_time = start + timedelta(minutes=deploy_minute)
    rows: list[tuple[datetime, int, str]] = []

    def add(ts, *args, **kwargs):
        rows.append((ts, len(rows), _line(ts, *args, **kwargs)))

    add(deploy_time, "INFO", "deploy-bot", "deployed payment-service", release=release)

    counter = 0
    for minute in range(minutes):
        for _ in range(requests_per_minute):
            counter += 1
            request_id = f"req-{counter:05d}"
            t0 = start + timedelta(minutes=minute, seconds=rng.randrange(0, 57))
            invalid_roll, timeout_roll = rng.random(), rng.random()

            timeout_rate = BASE_TIMEOUT_RATE
            if incident and t0 >= deploy_time:
                timeout_rate = min(BASE_TIMEOUT_RATE * multiplier, 0.9)

            add(t0, "INFO", "checkout-service", "order received", request_id)
            if invalid_roll < VALIDATION_ERROR_RATE:
                add(t0 + timedelta(seconds=1), "ERROR", "checkout-service", "invalid order payload",
                    request_id, "ValidationError")
                continue

            add(t0, "INFO", "payment-service", "charge started", request_id)
            if timeout_roll < timeout_rate:
                add(t0 + timedelta(seconds=1), "ERROR", "payment-service", "upstream timed out after 5000ms",
                    request_id, "TimeoutError")
                add(t0 + timedelta(seconds=2), "ERROR", "checkout-service", "payment call failed",
                    request_id, "UpstreamFailure")
            else:
                add(t0 + timedelta(seconds=1), "INFO", "payment-service", "charge ok", request_id)
                add(t0 + timedelta(seconds=1), "INFO", "checkout-service", "order complete", request_id)

    rows.sort(key=lambda r: (r[0], r[1]))
    return [row[2] for row in rows]
