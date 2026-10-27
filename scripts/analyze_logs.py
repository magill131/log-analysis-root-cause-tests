"""Analyze a log file for errors that started or jumped after a deploy.

    python scripts/analyze_logs.py data/incident.log
    python scripts/analyze_logs.py data/clean.log --fail-on-spike

Exit codes: 0 = done, 1 = a regression was found and --fail-on-spike was given,
2 = the file could not be read or has no deploy marker.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from analysis import analyze  # noqa: E402
from log_parser import parse_lines  # noqa: E402
from report import build_report  # noqa: E402


def main(argv=None, out=None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("logfile", type=Path)
    parser.add_argument("--release", help="release to analyze (default: the latest deploy in the log)")
    parser.add_argument("--window", type=int, default=15, help="minutes before and after the deploy (default 15)")
    parser.add_argument("--ratio", type=float, default=3.0, help="flag errors that grew this many times (default 3)")
    parser.add_argument("--min-count", type=int, default=10, help="ignore error types with fewer errors after the deploy (default 10)")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "incident_report.md", help="where to write the markdown report")
    parser.add_argument("--fail-on-spike", action="store_true", help="exit 1 if any regression is found")
    args = parser.parse_args(argv)

    try:
        lines = args.logfile.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"Cannot read {args.logfile}: {exc.strerror or exc}", file=out)
        return 2

    parsed = parse_lines(lines)
    try:
        analysis = analyze(parsed.events, args.release, args.window, args.ratio, args.min_count)
    except ValueError as exc:
        print(str(exc), file=out)
        return 2

    report = build_report(analysis, parsed.events, len(parsed.malformed), args.logfile.name)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    print(report, file=out)
    print(f"Report written to {args.report}", file=out)
    if analysis.findings and args.fail_on_spike:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
