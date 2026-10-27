"""Following one request across services, and finding what failed first."""

import pytest

from analysis import group_by_request, root_cause, root_cause_tally, trace_request
from generator import generate_logs
from helpers import DEPLOY_TIME, T0, ev
from log_parser import parse_lines


def test_trace_returns_only_events_for_that_request():
    events = [ev(0, request_id="r1"), ev(1, request_id="r2"), ev(2, request_id="r1")]
    assert [e.timestamp for e in trace_request(events, "r1")] == [T0, T0.replace(second=2)]


def test_trace_is_sorted_by_time_even_if_the_file_is_not():
    events = [ev(5, request_id="r1", service="b"), ev(1, request_id="r1", service="a")]
    assert [e.service for e in trace_request(events, "r1")] == ["a", "b"]


def test_events_in_the_same_second_keep_file_order():
    events = [ev(1, request_id="r1", service="first"), ev(1, request_id="r1", service="second")]
    assert [e.service for e in trace_request(events, "r1")] == ["first", "second"]


def test_unknown_request_id_gives_an_empty_trace():
    assert trace_request([ev(0, request_id="r1")], "nope") == []


def test_events_without_a_request_id_are_left_out_of_traces():
    assert group_by_request([ev(0), ev(1, request_id="r1")]).keys() == {"r1"}


def test_root_cause_is_the_first_error():
    trace = [
        ev(0, level="INFO", request_id="r"),
        ev(1, service="payment-service", request_id="r"),
        ev(2, service="checkout-service", error_type="UpstreamFailure", request_id="r"),
    ]
    assert root_cause(trace).service == "payment-service"


def test_root_cause_of_a_request_with_no_errors_is_none():
    assert root_cause([ev(0, level="INFO", request_id="r")]) is None


def test_root_cause_of_an_empty_trace_is_none():
    assert root_cause([]) is None


def test_tally_counts_which_error_started_each_affected_request():
    events = []
    for i in range(3):  # payment failed first, then checkout
        events += [
            ev(i * 10, service="payment-service", error_type="TimeoutError", request_id=f"p{i}"),
            ev(i * 10 + 1, service="checkout-service", error_type="UpstreamFailure", request_id=f"p{i}"),
        ]
    events.append(ev(100, service="checkout-service", error_type="UpstreamFailure", request_id="solo"))
    tally = root_cause_tally(events, "checkout-service", "UpstreamFailure")
    assert tally[("payment-service", "TimeoutError")] == 3
    assert tally[("checkout-service", "UpstreamFailure")] == 1


def test_tally_ignores_requests_without_the_error():
    events = [ev(0, service="a", error_type="X", request_id="r1"), ev(1, service="b", error_type="Y", request_id="r2")]
    assert sum(root_cause_tally(events, "a", "X").values()) == 1


def test_tally_respects_since_and_until():
    events = [ev(0, request_id="r1"), ev(1000, request_id="r2"), ev(3000, request_id="r3")]
    start, end = T0.replace(minute=10), T0.replace(minute=40)
    tally = root_cause_tally(events, "payment-service", "TimeoutError", since=start, until=end)
    assert sum(tally.values()) == 1


def test_tally_since_is_inclusive_and_until_is_exclusive():
    events = [ev(1800, request_id="r1"), ev(2700, request_id="r2")]
    tally = root_cause_tally(events, "payment-service", "TimeoutError", since=DEPLOY_TIME, until=T0.replace(minute=45))
    assert sum(tally.values()) == 1


@pytest.mark.parametrize("seed", range(1, 11))
def test_in_generated_logs_payment_always_fails_before_checkout(seed):
    """Every request that failed in both services started failing in payment-service."""
    events = parse_lines(generate_logs(seed=seed)).events
    checked = 0
    for trace in group_by_request(events).values():
        services = {e.service for e in trace if e.is_error}
        if {"payment-service", "checkout-service"} <= services and any(
            e.error_type == "UpstreamFailure" for e in trace
        ):
            assert root_cause(trace).service == "payment-service"
            checked += 1
    assert checked > 0
