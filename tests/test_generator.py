"""The log generator must be repeatable and produce valid, sensible logs."""

from datetime import timedelta

import pytest

from analysis import count_errors_by_type, find_deploys
from generator import DEFAULT_START, generate_logs
from log_parser import parse_lines


def test_same_seed_gives_the_same_log():
    assert generate_logs(seed=5) == generate_logs(seed=5)


def test_different_seeds_give_different_logs():
    assert generate_logs(seed=1) != generate_logs(seed=2)


def test_multiplier_of_one_matches_a_log_with_no_incident():
    assert generate_logs(seed=3, incident=True, multiplier=1) == generate_logs(seed=3, incident=False)


@pytest.mark.parametrize("seed", range(1, 11))
def test_every_generated_line_parses(seed):
    result = parse_lines(generate_logs(seed=seed))
    assert result.malformed == []
    assert result.events


@pytest.mark.parametrize("seed", range(1, 6))
def test_lines_are_in_time_order(seed):
    times = [e.timestamp for e in parse_lines(generate_logs(seed=seed)).events]
    assert times == sorted(times)


def test_there_is_exactly_one_deploy_marker_at_the_requested_minute():
    events = parse_lines(generate_logs(seed=1, deploy_minute=12, release="v9.9")).events
    assert find_deploys(events) == [(DEFAULT_START + timedelta(minutes=12), "v9.9")]


def test_log_covers_the_requested_number_of_minutes():
    events = parse_lines(generate_logs(seed=1, minutes=10, deploy_minute=5)).events
    assert events[0].timestamp >= DEFAULT_START
    assert events[-1].timestamp < DEFAULT_START + timedelta(minutes=10, seconds=5)


def test_request_count_matches_the_rate():
    events = parse_lines(generate_logs(seed=1, minutes=10, deploy_minute=5, requests_per_minute=7)).events
    received = [e for e in events if e.message == "order received"]
    assert len(received) == 70


def test_request_ids_are_unique_per_request():
    events = parse_lines(generate_logs(seed=1)).events
    received = [e.request_id for e in events if e.message == "order received"]
    assert len(received) == len(set(received))


def test_every_payment_timeout_is_followed_by_a_checkout_failure_for_the_same_request():
    events = parse_lines(generate_logs(seed=2)).events
    timeouts = {e.request_id: e for e in events if e.error_type == "TimeoutError"}
    failures = {e.request_id: e for e in events if e.error_type == "UpstreamFailure"}
    assert timeouts and timeouts.keys() == failures.keys()
    for rid, timeout in timeouts.items():
        assert failures[rid].timestamp - timeout.timestamp == timedelta(seconds=1)


@pytest.mark.parametrize("seed", range(1, 8))
def test_incident_log_has_more_payment_timeouts_after_the_deploy(seed):
    events = parse_lines(generate_logs(seed=seed)).events
    deploy_time = find_deploys(events)[0][0]
    before = sum(1 for e in events if e.error_type == "TimeoutError" and e.timestamp < deploy_time)
    after = sum(1 for e in events if e.error_type == "TimeoutError" and e.timestamp >= deploy_time)
    assert after > 3 * before


def test_clean_log_has_no_big_change_in_timeouts_at_the_deploy():
    events = parse_lines(generate_logs(seed=1, incident=False)).events
    deploy_time = find_deploys(events)[0][0]
    before = sum(1 for e in events if e.error_type == "TimeoutError" and e.timestamp < deploy_time)
    after = sum(1 for e in events if e.error_type == "TimeoutError" and e.timestamp >= deploy_time)
    assert after < 3 * max(before, 1)


def test_log_contains_the_expected_error_types_only():
    events = parse_lines(generate_logs(seed=4)).events
    types = {key[1] for key in count_errors_by_type(events)}
    assert types <= {"TimeoutError", "UpstreamFailure", "ValidationError"}


def test_extreme_multiplier_is_capped_so_some_payments_still_succeed():
    events = parse_lines(generate_logs(seed=1, multiplier=1000)).events
    after_ok = [e for e in events if e.message == "charge ok" and e.timestamp >= DEFAULT_START + timedelta(minutes=20)]
    assert after_ok
