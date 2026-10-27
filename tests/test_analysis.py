"""Before/after comparison and the flag rule."""

from datetime import timedelta

import pytest

from analysis import (
    analyze,
    compare_before_after,
    count_errors_by_type,
    find_deploys,
)
from helpers import DEPLOY_OFFSET, DEPLOY_TIME, T0, after_deploy, before_deploy, deploy, errors, ev


def flagged(events, **kwargs):
    findings, _, _ = compare_before_after(events, DEPLOY_TIME, **kwargs)
    return findings


# ---- counting ----

def test_counts_errors_by_service_and_type():
    events = errors(3, 0) + errors(2, 10, service="checkout-service", error_type="UpstreamFailure")
    counts = count_errors_by_type(events)
    assert counts[("payment-service", "TimeoutError")] == 3
    assert counts[("checkout-service", "UpstreamFailure")] == 2


def test_non_error_events_are_not_counted():
    events = [ev(0, level="INFO"), ev(1, level="WARN"), ev(2)]
    assert sum(count_errors_by_type(events).values()) == 1


def test_error_without_a_type_is_counted_as_unknown():
    assert count_errors_by_type([ev(0, error_type=None)])[("payment-service", "unknown")] == 1


def test_same_error_type_in_two_services_is_counted_separately():
    events = [ev(0, service="a"), ev(1, service="b")]
    counts = count_errors_by_type(events)
    assert counts[("a", "TimeoutError")] == 1 and counts[("b", "TimeoutError")] == 1


# ---- deploy markers ----

def test_find_deploys_returns_them_sorted_by_time():
    events = [deploy(500, "v2"), deploy(100, "v1")]
    assert [release for _, release in find_deploys(events)] == ["v1", "v2"]


def test_only_deploy_bot_events_with_a_release_are_deploys():
    events = [ev(0, service="payment-service", release="v9"), ev(1, service="deploy-bot", release=None)]
    assert find_deploys(events) == []


# ---- the flag rule ----

def test_spike_is_flagged_at_exactly_the_ratio_threshold():
    events = before_deploy(4) + after_deploy(12)
    assert [f.kind for f in flagged(events)] == ["spike"]


def test_growth_just_under_the_threshold_is_not_flagged():
    events = before_deploy(4) + after_deploy(11)  # 2.75x
    assert flagged(events) == []


def test_small_counts_are_not_flagged_even_when_the_ratio_is_huge():
    events = before_deploy(1) + after_deploy(9)
    assert flagged(events) == []


def test_count_exactly_at_the_minimum_is_flagged():
    events = before_deploy(1) + after_deploy(10)
    assert len(flagged(events)) == 1


def test_new_error_type_is_flagged_as_new():
    findings = flagged(after_deploy(10))
    assert [(f.kind, f.before_count, f.ratio) for f in findings] == [("new", 0, None)]


def test_new_error_type_below_the_minimum_is_not_flagged():
    assert flagged(after_deploy(9)) == []


def test_error_that_stops_after_the_deploy_is_not_flagged():
    assert flagged(before_deploy(20)) == []


def test_error_that_decreases_is_not_flagged():
    assert flagged(before_deploy(40) + after_deploy(12)) == []


def test_steady_error_rate_is_not_flagged():
    assert flagged(before_deploy(12) + after_deploy(12)) == []


def test_finding_reports_both_counts_and_the_ratio():
    finding = flagged(before_deploy(5) + after_deploy(25))[0]
    assert (finding.before_count, finding.after_count, finding.ratio) == (5, 25, 5.0)


def test_each_service_and_error_type_is_judged_on_its_own():
    events = (
        before_deploy(5) + after_deploy(5)  # steady
        + before_deploy(2, service="checkout-service", error_type="UpstreamFailure")
        + after_deploy(20, service="checkout-service", error_type="UpstreamFailure")
    )
    assert [(f.service, f.error_type) for f in flagged(events)] == [("checkout-service", "UpstreamFailure")]


def test_findings_are_sorted_by_errors_after_the_deploy():
    events = (
        before_deploy(1, error_type="A") + after_deploy(12, error_type="A")
        + before_deploy(1, error_type="B") + after_deploy(30, error_type="B")
    )
    assert [f.error_type for f in flagged(events)] == ["B", "A"]


def test_custom_ratio_threshold_is_used():
    events = before_deploy(4) + after_deploy(12)
    assert flagged(events, ratio_threshold=4.0) == []


def test_custom_min_count_is_used():
    events = before_deploy(1) + after_deploy(5)
    assert len(flagged(events, min_count=5)) == 1


# ---- window edges ----

def totals(events, **kwargs):
    _, before, after = compare_before_after(events, DEPLOY_TIME, **kwargs)
    return before, after


def test_error_exactly_at_the_deploy_time_counts_as_after():
    assert totals([ev(DEPLOY_OFFSET)]) == (0, 1)


def test_error_one_second_before_the_deploy_counts_as_before():
    assert totals([ev(DEPLOY_OFFSET - 1)]) == (1, 0)


def test_error_exactly_one_window_before_the_deploy_counts_as_before():
    assert totals([ev(DEPLOY_OFFSET - 900)]) == (1, 0)


def test_error_older_than_the_window_is_ignored():
    assert totals([ev(DEPLOY_OFFSET - 901)]) == (0, 0)


def test_error_exactly_one_window_after_the_deploy_is_ignored():
    assert totals([ev(DEPLOY_OFFSET + 900)]) == (0, 0)


def test_error_just_inside_the_after_window_counts():
    assert totals([ev(DEPLOY_OFFSET + 899)]) == (0, 1)


def test_window_size_is_configurable():
    events = [ev(DEPLOY_OFFSET - 200), ev(DEPLOY_OFFSET + 200)]
    assert totals(events, window_minutes=5) == (1, 1)
    assert totals(events, window_minutes=3) == (0, 0)


# ---- analyze ----

def test_analyze_without_a_deploy_marker_raises():
    with pytest.raises(ValueError, match="No deploy marker"):
        analyze(errors(5, 0))


def test_analyze_uses_the_latest_deploy_by_default():
    analysis = analyze([deploy(100, "v1"), deploy(5000, "v2")])
    assert analysis.release == "v2"
    assert analysis.deploy_time == T0 + timedelta(seconds=5000)


def test_analyze_can_pick_a_named_release():
    analysis = analyze([deploy(100, "v1"), deploy(5000, "v2")], release="v1")
    assert analysis.release == "v1"


def test_analyze_unknown_release_raises():
    with pytest.raises(ValueError, match="'v9'"):
        analyze([deploy(100, "v1")], release="v9")


def test_analyze_returns_findings_and_totals():
    events = [deploy()] + before_deploy(3) + after_deploy(30)
    analysis = analyze(events)
    assert (analysis.before_errors, analysis.after_errors) == (3, 30)
    assert len(analysis.findings) == 1


def test_analyze_passes_thresholds_through():
    events = [deploy()] + before_deploy(4) + after_deploy(12)
    assert len(analyze(events).findings) == 1
    assert analyze(events, ratio_threshold=5).findings == []
    assert analyze(events, min_count=13).findings == []
    # A 1-minute window sees none of the earlier errors, so the same errors now look new.
    assert [f.kind for f in analyze(events, window_minutes=1).findings] == ["new"]
