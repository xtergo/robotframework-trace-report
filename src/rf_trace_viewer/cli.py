"""CLI entry point for rf-trace-report."""

from __future__ import annotations

import argparse
import os
import sys

from rf_trace_viewer import __version__
from rf_trace_viewer.generator import ReportOptions, generate_report
from rf_trace_viewer.parser import parse_file
from rf_trace_viewer.rf_model import interpret_tree
from rf_trace_viewer.tree import build_tree


def _add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared between the default command and the serve subcommand."""
    parser.add_argument(
        "-o",
        "--output",
        default="trace-report.html",
        help="Output HTML file path (default: trace-report.html)",
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
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="Polling interval in seconds for live mode (default: 5, range: 1-30)",
    )
    parser.add_argument(
        "--compact-html",
        action="store_true",
        help="Omit default-value fields from embedded JSON to reduce file size",
    )
    parser.add_argument(
        "--gzip-embed",
        action="store_true",
        help="Gzip-compress and base64-encode embedded JSON data to reduce file size",
    )
    parser.add_argument(
        "--max-keyword-depth",
        type=int,
        default=None,
        metavar="N",
        help="Truncate keyword children beyond depth N (1 = only top-level keywords)",
    )
    parser.add_argument(
        "--exclude-passing-keywords",
        action="store_true",
        help="Exclude keyword spans with PASS status from the report (keeps FAIL/SKIP/NOT_RUN)",
    )
    parser.add_argument(
        "--max-spans",
        type=int,
        default=None,
        metavar="N",
        help="Limit total spans in the report to N, prioritising FAIL > SKIP > PASS (shallowest first)",
    )
    parser.add_argument(
        "--receiver",
        action="store_true",
        help="Start live server in OTLP receiver mode (no input file required)",
    )
    parser.add_argument(
        "--journal",
        default="traces.journal.json",
        metavar="<path>",
        help="Journal file path for crash recovery (default: traces.journal.json)",
    )
    parser.add_argument(
        "--no-journal",
        action="store_true",
        help="Disable journal file writing in receiver mode",
    )
    parser.add_argument(
        "--forward",
        default=None,
        metavar="<url>",
        help="Forward received OTLP payloads to an upstream collector URL",
    )

    # Provider and SigNoz arguments
    parser.add_argument(
        "--provider",
        choices=["json", "signoz"],
        default="json",
        help="Trace data provider (default: json)",
    )
    parser.add_argument(
        "--signoz-endpoint",
        default=None,
        metavar="<url>",
        help="SigNoz API base URL (required when --provider signoz)",
    )
    parser.add_argument(
        "--signoz-api-key",
        default=None,
        help="SigNoz API key (also readable from SIGNOZ_API_KEY env var)",
    )
    parser.add_argument(
        "--execution-attribute",
        default="essvt.execution_id",
        help="Span attribute name for grouping executions (default: essvt.execution_id)",
    )
    parser.add_argument(
        "--max-spans-per-page",
        type=int,
        default=10000,
        metavar="N",
        help="Page size for paged span retrieval (default: 10000)",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="<path>",
        help="Path to JSON configuration file",
    )
    parser.add_argument(
        "--overlap-window",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Overlap window in seconds for live poll deduplication (default: 2.0)",
    )


def _validate_provider_config(args: argparse.Namespace) -> str | None:
    """Validate provider configuration. Returns error message or None."""
    if args.provider == "signoz":
        endpoint = args.signoz_endpoint or os.environ.get("SIGNOZ_ENDPOINT")
        if not endpoint:
            return (
                "Error: --provider signoz requires --signoz-endpoint "
                "(via CLI, config file, or SIGNOZ_ENDPOINT env var)"
            )
    return None


def _build_report_options(args: argparse.Namespace) -> ReportOptions:
    """Build ReportOptions from parsed arguments."""
    return ReportOptions(
        title=args.title,
        compact=args.compact_html,
        gzip_embed=args.gzip_embed,
        max_keyword_depth=args.max_keyword_depth,
        exclude_passing_keywords=args.exclude_passing_keywords,
        max_spans=args.max_spans,
    )


def _run_live_server(args: argparse.Namespace) -> int:
    """Start the live HTTP server. Returns exit code."""
    from rf_trace_viewer.server import LiveServer

    # Validate provider config
    error = _validate_provider_config(args)
    if error:
        print(error, file=sys.stderr)
        return 1

    trace_path = getattr(args, "input", None) or ""

    journal_path = None if args.no_journal else args.journal
    report_options = _build_report_options(args)

    server = LiveServer(
        trace_path=trace_path,
        port=args.port,
        title=args.title,
        poll_interval=args.poll_interval,
        receiver_mode=args.receiver,
        journal_path=journal_path,
        forward_url=args.forward,
        output_path=args.output,
        report_options=report_options,
    )
    server.start(open_browser=not args.no_open)
    return 0


def _is_serve_subcommand() -> bool:
    """Check if the first non-option argument in sys.argv is 'serve'."""
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            continue
        return arg == "serve"
    return False


def _build_serve_parser() -> argparse.ArgumentParser:
    """Build the parser for the 'serve' subcommand."""
    parser = argparse.ArgumentParser(
        prog="rf-trace-report serve",
        description="Start HTTP server for live trace viewing without requiring an input file",
    )
    _add_shared_arguments(parser)
    return parser


def _build_default_parser() -> argparse.ArgumentParser:
    """Build the default (legacy) parser."""
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
        nargs="?",
        default=None,
        help="Trace file path (.json or .json.gz), or - for stdin",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Start live server instead of generating static file",
    )
    _add_shared_arguments(parser)
    return parser


def main() -> int:
    """CLI entry point. Returns 0 on success, 1 on error."""

    # Detect 'serve' subcommand before argparse to avoid positional arg conflict
    if _is_serve_subcommand():
        parser = _build_serve_parser()
        # Strip 'serve' from argv before parsing
        args = parser.parse_args(sys.argv[2:])
        args.live = True
        return _run_live_server(args)

    # Default (legacy) parser
    parser = _build_default_parser()
    args = parser.parse_args()

    # Receiver mode implies live mode
    if args.receiver:
        args.live = True

    # Live mode
    if args.live:
        return _run_live_server(args)

    # Static mode requires an input file
    if args.input is None:
        print("Error: input file is required (or use --receiver or serve)", file=sys.stderr)
        return 1

    # Static mode pipeline: parse → build tree → interpret → generate → write
    try:
        spans = parse_file(args.input)
        roots = build_tree(spans)
        model = interpret_tree(roots)

        options = _build_report_options(args)
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
