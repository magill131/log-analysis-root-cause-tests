from analysis import analyze
from generator import generate_logs
from helpers import DEPLOY_OFFSET, after_deploy, before_deploy, deploy, ev
from log_parser import parse_lines
from report import build_report


def incident_report(seed=7, malformed=0):
    events = parse_lines(generate_logs(seed=seed)).events
    analysis = analyze(events)
    return analysis, build_report(analysis, events, malformed, "incident.log")


def test_report_names_the_release_log_and_deploy_time():
    _, report = incident_report()
    assert report.startswith("# Incident report: release v2.3.1")
    assert "`incident.log`" in report
    assert "2026-03-02 14:20:00 UTC" in report


def test_report_table_has_a_row_for_every_finding():
    analysis, report = incident_report()
    assert analysis.findings
    for f in analysis.findings:
        assert f"| {f.service} | {f.error_type} | {f.before_count} | {f.after_count} |" in report


def test_report_shows_the_change_as_a_multiple():
    analysis, report = incident_report()
    assert f"{analysis.findings[0].ratio:.1f}x" in report


def test_report_points_to_the_upstream_service_as_the_root_cause():
    _, report = incident_report()
    assert "first failed in payment-service with TimeoutError" in report
    assert "(100%)" in report


def test_report_includes_an_example_trace_in_time_order():
    _, report = incident_report()
    trace = report.split("```")[1]
    assert trace.index("charge started") < trace.index("upstream timed out") < trace.index("payment call failed")


def test_report_shows_the_malformed_line_count():
    _, report = incident_report(malformed=4)
    assert "Malformed lines skipped: 4." in report


def test_report_with_no_findings_says_so_and_skips_the_other_sections():
    events = parse_lines(generate_logs(seed=1, incident=False)).events
    analysis = analyze(events)
    assert analysis.findings == []
    report = build_report(analysis, events, 0, "clean.log")
    assert "No regressions found." in report
    assert "Likely root cause" not in report


def test_report_shows_new_error_types_as_new():
    events = [deploy()] + after_deploy(12)
    report = build_report(analyze(events), events, 0, "x.log")
    assert "| new |" in report


def test_report_states_the_rule_used_to_flag_errors():
    _, report = incident_report()
    assert "at least 10 errors" in report and "3x" in report
