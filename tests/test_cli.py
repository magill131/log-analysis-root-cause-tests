import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_logs import main  # noqa: E402
from generator import generate_logs  # noqa: E402


@pytest.fixture
def incident_log(tmp_path):
    path = tmp_path / "incident.log"
    path.write_text("\n".join(generate_logs(seed=7)) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def clean_log(tmp_path):
    path = tmp_path / "clean.log"
    path.write_text("\n".join(generate_logs(seed=7, incident=False)) + "\n", encoding="utf-8")
    return path


def run(args, tmp_path):
    out = io.StringIO()
    code = main([*map(str, args), "--report", str(tmp_path / "report.md")], out=out)
    return code, out.getvalue()


def test_incident_log_exits_zero_by_default(incident_log, tmp_path):
    code, output = run([incident_log], tmp_path)
    assert code == 0
    assert "payment-service" in output


def test_fail_on_spike_exits_one_when_a_regression_is_found(incident_log, tmp_path):
    assert run([incident_log, "--fail-on-spike"], tmp_path)[0] == 1


def test_fail_on_spike_exits_zero_for_a_clean_log(clean_log, tmp_path):
    code, output = run([clean_log, "--fail-on-spike"], tmp_path)
    assert code == 0
    assert "No regressions found." in output


def test_report_file_is_written(incident_log, tmp_path):
    run([incident_log], tmp_path)
    assert "# Incident report" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_missing_file_exits_two_with_a_message(tmp_path):
    code, output = run([tmp_path / "nope.log"], tmp_path)
    assert code == 2
    assert "Cannot read" in output


def test_log_without_a_deploy_marker_exits_two(tmp_path):
    path = tmp_path / "nodeploy.log"
    path.write_text("2026-03-02T14:00:00Z ERROR svc error_type=X\n", encoding="utf-8")
    code, output = run([path], tmp_path)
    assert code == 2
    assert "No deploy marker" in output


def test_unknown_release_exits_two(incident_log, tmp_path):
    code, output = run([incident_log, "--release", "v0.0.1"], tmp_path)
    assert code == 2
    assert "v0.0.1" in output


def test_named_release_can_be_analyzed(incident_log, tmp_path):
    code, output = run([incident_log, "--release", "v2.3.1"], tmp_path)
    assert code == 0 and "release v2.3.1" in output


def test_malformed_lines_are_skipped_and_counted(incident_log, tmp_path):
    with incident_log.open("a", encoding="utf-8") as f:
        f.write("this is not a log line\n???\n")
    code, output = run([incident_log], tmp_path)
    assert code == 0
    assert "Malformed lines skipped: 2." in output


def test_higher_ratio_option_turns_the_flag_off(incident_log, tmp_path):
    assert run([incident_log, "--ratio", "100", "--fail-on-spike"], tmp_path)[0] == 0


def test_higher_min_count_option_turns_the_flag_off(incident_log, tmp_path):
    assert run([incident_log, "--min-count", "1000", "--fail-on-spike"], tmp_path)[0] == 0


def test_window_option_is_used(incident_log, tmp_path):
    _, output = run([incident_log, "--window", "5"], tmp_path)
    assert "Compared the 5 minutes before" in output


def test_committed_sample_logs_give_the_expected_results(tmp_path):
    incident = ROOT / "data" / "incident.log"
    clean = ROOT / "data" / "clean.log"
    assert run([incident, "--fail-on-spike"], tmp_path)[0] == 1
    assert run([clean, "--fail-on-spike"], tmp_path)[0] == 0
