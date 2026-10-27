"""How good is the detector itself?

The detector is statistical, so it can raise a false alarm on a quiet log or
miss a real incident, because the generated logs have random noise. These tests
measure that over many seeds and fix the measured rates as a floor, so a change
that makes the detector worse fails the suite. The numbers are the same on
every run because every log comes from a seed.

(Measured over 500 seeds when this was written: 3 false alarms on clean logs,
and 492 of 500 incidents at 10x detected.)
"""

from functools import lru_cache

import pytest

from analysis import analyze
from generator import generate_logs
from log_parser import parse_lines

PAYMENT = ("payment-service", "TimeoutError")
CASCADE = ("checkout-service", "UpstreamFailure")


@lru_cache(maxsize=None)
def flagged_keys(seed, incident=True, multiplier=10.0):
    events = parse_lines(generate_logs(seed=seed, incident=incident, multiplier=multiplier)).events
    return frozenset((f.service, f.error_type) for f in analyze(events).findings)


def detection_count(multiplier, seeds):
    return sum(PAYMENT in flagged_keys(s, True, float(multiplier)) for s in seeds)


def test_clean_logs_rarely_raise_a_false_alarm():
    false_alarms = sum(bool(flagged_keys(s, False, 10.0)) for s in range(1, 101))
    assert false_alarms <= 3  # measured: 1 of 100


def test_a_10x_incident_is_detected_in_nearly_every_log():
    assert detection_count(10, range(1, 101)) >= 97  # measured: 100 of 100


def test_the_downstream_failure_is_flagged_along_with_the_cause():
    both = sum(
        PAYMENT in flagged_keys(s, True, 10.0) and CASCADE in flagged_keys(s, True, 10.0)
        for s in range(1, 101)
    )
    assert both >= 97  # measured: 100 of 100


def test_no_incident_is_never_flagged_as_a_payment_timeout_spike():
    assert detection_count(1, range(1, 51)) == 0


def test_detection_gets_better_as_the_incident_gets_bigger():
    counts = [detection_count(m, range(1, 51)) for m in (1, 3, 5, 8, 10)]
    assert counts == sorted(counts)  # measured: 0, 6, 25, 46, 50 of 50


def test_a_small_incident_is_often_missed_which_is_the_detectors_known_limit():
    assert detection_count(3, range(1, 51)) < 25  # measured: 6 of 50


@pytest.mark.xfail(
    strict=True,
    reason="Known false alarm: clean seed 6 has only 2 ValidationErrors before the deploy by chance, "
    "so 13 after looks like a 6.5x spike. Ratios of small counts are noisy.",
)
def test_clean_log_for_seed_6_is_not_flagged():
    assert flagged_keys(6, False, 10.0) == frozenset()
