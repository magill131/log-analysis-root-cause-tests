"""Small builders for hand-made log events."""

from datetime import datetime, timedelta, timezone

from log_parser import LogEvent

T0 = datetime(2026, 3, 2, 14, 0, 0, tzinfo=timezone.utc)
DEPLOY_OFFSET = 1800  # the deploy happens 30 minutes after T0
DEPLOY_TIME = T0 + timedelta(seconds=DEPLOY_OFFSET)


def ev(offset_s=0, level="ERROR", service="payment-service", error_type="TimeoutError",
       request_id=None, release=None, msg=""):
    return LogEvent(T0 + timedelta(seconds=offset_s), level, service, msg, request_id, error_type, release)


def deploy(offset_s=DEPLOY_OFFSET, release="v1"):
    return LogEvent(T0 + timedelta(seconds=offset_s), "INFO", "deploy-bot", "deployed", None, None, release)


def errors(count, start_offset_s, service="payment-service", error_type="TimeoutError", step_s=1):
    """`count` ERROR events, one every `step_s` seconds, starting at `start_offset_s`."""
    return [ev(start_offset_s + i * step_s, service=service, error_type=error_type) for i in range(count)]


def before_deploy(count, **kwargs):
    """Errors spread across the 15 minutes before the deploy."""
    return errors(count, DEPLOY_OFFSET - 800, **kwargs)


def after_deploy(count, **kwargs):
    """Errors spread across the 15 minutes after the deploy."""
    return errors(count, DEPLOY_OFFSET + 10, **kwargs)
