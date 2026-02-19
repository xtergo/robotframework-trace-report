"""CLI entry point for rf-trace-report."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="rf-trace-report",
        description="Generate HTML reports from Robot Framework OpenTelemetry trace files",
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

    # TODO: Implement static and live modes
    print(f"rf-trace-report v0.1.0")
    print(f"Input: {args.input}")
    if args.live:
        print(f"Live mode on port {args.port}")
    else:
        print(f"Output: {args.output}")
    print("Not yet implemented — see TODO.md for roadmap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
