from datetime import datetime, timezone

import pytest

from log_parser import ParseError, parse_line, parse_lines

FULL = (
    '2026-03-02T14:05:11Z ERROR payment-service request_id=req-00042 '
    'error_type=TimeoutError msg="upstream timed out"'
)


def test_parses_every_field_of_a_full_line():
    event = parse_line(FULL)
    assert event.timestamp == datetime(2026, 3, 2, 14, 5, 11, tzinfo=timezone.utc)
    assert event.level == "ERROR"
    assert event.service == "payment-service"
    assert event.request_id == "req-00042"
    assert event.error_type == "TimeoutError"
    assert event.message == "upstream timed out"
    assert event.is_error


def test_line_with_no_fields_is_valid():
    event = parse_line("2026-03-02T14:00:00Z INFO checkout-service")
    assert event.message == "" and event.request_id is None and event.error_type is None


def test_info_event_is_not_an_error():
    assert not parse_line("2026-03-02T14:00:00Z INFO svc").is_error


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARN", "ERROR"])
def test_all_four_levels_are_accepted(level):
    assert parse_line(f"2026-03-02T14:00:00Z {level} svc").level == level


def test_timestamp_is_utc_aware():
    assert parse_line("2026-03-02T14:00:00Z INFO svc").timestamp.tzinfo == timezone.utc


def test_deploy_line_exposes_the_release():
    event = parse_line('2026-03-02T14:20:00Z INFO deploy-bot release=v2.3.1 msg="deployed payment-service"')
    assert event.release == "v2.3.1"


def test_unquoted_value_is_read_as_is():
    assert parse_line("2026-03-02T14:00:00Z INFO svc request_id=abc-1").request_id == "abc-1"


def test_quoted_message_keeps_its_spaces():
    assert parse_line('2026-03-02T14:00:00Z INFO svc msg="a b  c"').message == "a b  c"


def test_escaped_quote_inside_a_message():
    assert parse_line(r'2026-03-02T14:00:00Z INFO svc msg="say \"hi\""').message == 'say "hi"'


def test_equals_sign_inside_a_quoted_message_is_not_a_field():
    event = parse_line('2026-03-02T14:00:00Z INFO svc msg="a=b c=d"')
    assert event.message == "a=b c=d"
    assert set(event.fields) == {"msg"}


def test_extra_fields_are_kept():
    event = parse_line("2026-03-02T14:00:00Z INFO svc region=us-east retries=3")
    assert event.fields == {"region": "us-east", "retries": "3"}


def test_surrounding_whitespace_and_newline_are_ignored():
    assert parse_line("  2026-03-02T14:00:00Z INFO svc  \n").service == "svc"


def test_tabs_and_repeated_spaces_between_parts_are_allowed():
    event = parse_line("2026-03-02T14:00:00Z\tINFO   svc \t request_id=r1")
    assert event.request_id == "r1"


@pytest.mark.parametrize(
    "line, reason",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("garbage", "expected"),
        ("2026-03-02T14:00:00Z", "expected"),
        ("2026-03-02T14:00:00Z INFO", "expected"),
        ("2026-03-02 14:00:00 INFO svc", "bad timestamp"),
        ("2026-13-02T14:00:00Z INFO svc", "bad timestamp"),
        ("2026-03-02T14:00:00 INFO svc", "bad timestamp"),
        ("2026-03-02T14:00:00Z NOTICE svc", "unknown level"),
        ("2026-03-02T14:00:00Z info svc", "unknown level"),
        ("2026-03-02T14:00:00Z WARNING svc", "unknown level"),
        ('2026-03-02T14:00:00Z INFO svc msg="never closed', "bad field"),
        ("2026-03-02T14:00:00Z INFO svc justaword", "bad field"),
        ("2026-03-02T14:00:00Z INFO svc key=", "bad field"),
        ("2026-03-02T14:00:00Z INFO svc a=1 a=2", "duplicate field"),
    ],
)
def test_malformed_line_is_rejected_with_a_reason(line, reason):
    with pytest.raises(ParseError, match=reason):
        parse_line(line)


def test_parse_lines_returns_events_in_order():
    result = parse_lines([
        "2026-03-02T14:00:02Z INFO a",
        "2026-03-02T14:00:01Z INFO b",
    ])
    assert [e.service for e in result.events] == ["a", "b"]
    assert result.malformed == []


def test_parse_lines_skips_blank_lines_without_reporting_them():
    result = parse_lines(["", "2026-03-02T14:00:00Z INFO a", "   ", "\n"])
    assert len(result.events) == 1 and result.malformed == []


def test_parse_lines_collects_malformed_lines_with_line_numbers():
    result = parse_lines([
        "2026-03-02T14:00:00Z INFO a",
        "not a log line",
        "",
        "2026-03-02T14:00:01Z NOPE b",
        "2026-03-02T14:00:02Z INFO c",
    ])
    assert [e.service for e in result.events] == ["a", "c"]
    assert [(m.line_number, m.line) for m in result.malformed] == [
        (2, "not a log line"),
        (4, "2026-03-02T14:00:01Z NOPE b"),
    ]
    assert "unknown level" in result.malformed[1].reason


def test_parse_lines_with_only_bad_lines_returns_no_events():
    result = parse_lines(["x", "y"])
    assert result.events == [] and len(result.malformed) == 2


def test_parse_lines_accepts_any_iterable():
    result = parse_lines(iter(["2026-03-02T14:00:00Z INFO a"]))
    assert len(result.events) == 1
