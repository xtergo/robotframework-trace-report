"""CLI entry point for rf-trace-report."""

from __future__ import annotations

import argparse
import sys

from rf_trace_viewer import __version__
from rf_trace_viewer.generator import ReportOptions, generate_report
from rf_trace_viewer.parser import parse_file
from rf_trace_viewer.rf_model import interpret_tree
from rf_trace_viewer.tree import build_tree


def main() -> int:
    """CLI entry point. Returns 0 on success, 1 on error."""
    parser = argparse.ArgumentParser(
        prog="rf-trace-report",
        description="Generate HTML reports from Robot Framework OpenTelemetry trace files",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "input",
        help="Trace file path (.json or .json.gz), or - for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="trace-report.html",
        help="Output HTML file path (default: trace-report.html)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Start live server instead of generating static file",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8077,
        help="Port for live server (default: 8077)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Report title (default: derived from trace data)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't auto-open browser in live mode",
    )

    args = parser.parse_args()

    # Live mode — not yet implemented
    if args.live:
        print("Live mode not yet implemented")
        return 0

    # Static mode pipeline: parse → build tree → interpret → generate → write
    try:
        spans = parse_file(args.input)
        roots = build_tree(spans)
        model = interpret_tree(roots)

        options = ReportOptions(title=args.title)
        html = generate_report(model, options)

        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)

        test_count = model.statistics.total_tests
        passed = model.statistics.passed
        failed = model.statistics.failed
        skipped = model.statistics.skipped
        print(
            f"Report generated: {args.output} "
            f"({len(spans)} spans, {test_count} tests: "
            f"{passed} passed, {failed} failed, {skipped} skipped)"
        )
        return 0

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"Error: Permission denied — {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
