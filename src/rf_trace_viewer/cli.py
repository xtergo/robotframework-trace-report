"""CLI entry point for rf-trace-report."""

from __future__ import annotations

import argparse
import sys

from rf_trace_viewer import __version__
from rf_trace_viewer.config import AppConfig, SigNozConfig, load_config
from rf_trace_viewer.exceptions import ConfigurationError
from rf_trace_viewer.generator import ReportOptions, generate_report
from rf_trace_viewer.parser import RawSpan, parse_file
from rf_trace_viewer.providers.base import TraceProvider, TraceSpan
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
        default="execution_id",
        help="Span attribute name for grouping executions (default: execution_id)",
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
    parser.add_argument(
        "--base-url",
        default=None,
        metavar="<url>",
        help="Base URL path for reverse proxy deployment (e.g. /trace-viewer)",
    )
    parser.add_argument(
        "--lookback",
        default=None,
        metavar="<duration>",
        help="Only fetch spans from the last N duration on startup (e.g. 10m, 1h, 30s). "
        "Default: fetch all. Applies to live/SigNoz mode only.",
    )
    parser.add_argument(
        "--service-name",
        default=None,
        metavar="<name>",
        help="Filter SigNoz spans by service.name (e.g. robot-framework). "
        "Also settable via ?service=<name> URL param by end users.",
    )
    parser.add_argument(
        "--signoz-jwt-secret",
        default=None,
        help="JWT signing secret for self-hosted SigNoz token auto-refresh "
        "(also readable from SIGNOZ_JWT_SECRET env var)",
    )
    parser.add_argument(
        "--logo-path",
        default=None,
        metavar="<path>",
        help="Path to a custom SVG logo file for the viewer header",
    )


def _args_to_cli_dict(args: argparse.Namespace) -> dict:
    """Convert argparse Namespace to a dict for load_config().

    Maps CLI argument names to AppConfig field names.
    Only includes explicitly provided (non-None) values.
    """
    mapping = {
        "provider": "provider",
        "input": "input_path",
        "output": "output_path",
        "live": "live",
        "port": "port",
        "title": "title",
        "signoz_endpoint": "signoz_endpoint",
        "signoz_api_key": "signoz_api_key",
        "execution_attribute": "execution_attribute",
        "poll_interval": "poll_interval",
        "max_spans_per_page": "max_spans_per_page",
        "max_spans": "max_spans",
        "overlap_window": "overlap_window_seconds",
        "receiver": "receiver",
        "forward": "forward",
        "journal": "journal",
        "no_journal": "no_journal",
        "no_open": "no_open",
        "compact_html": "compact_html",
        "gzip_embed": "gzip_embed",
        "base_url": "base_url",
        "lookback": "lookback",
        "service_name": "service_name",
        "signoz_jwt_secret": "signoz_jwt_secret",
        "logo_path": "logo_path",
    }
    result = {}
    for arg_name, config_name in mapping.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            result[config_name] = val
    return result


def _build_report_options(args: argparse.Namespace, logo_path: str | None = None) -> ReportOptions:
    """Build ReportOptions from parsed arguments."""
    return ReportOptions(
        title=args.title,
        compact=args.compact_html,
        gzip_embed=args.gzip_embed,
        max_keyword_depth=args.max_keyword_depth,
        exclude_passing_keywords=args.exclude_passing_keywords,
        max_spans=args.max_spans,
        logo_path=logo_path,
    )


def _trace_span_to_raw_span(ts: TraceSpan) -> RawSpan:
    """Convert a canonical TraceSpan to a RawSpan for the existing pipeline."""
    status_code_map = {
        "OK": "STATUS_CODE_OK",
        "ERROR": "STATUS_CODE_ERROR",
        "UNSET": "STATUS_CODE_UNSET",
    }
    status = {"code": status_code_map.get(ts.status, "STATUS_CODE_UNSET")}
    if ts.status_message:
        status["message"] = ts.status_message

    return RawSpan(
        trace_id=ts.trace_id,
        span_id=ts.span_id,
        parent_span_id=ts.parent_span_id,
        name=ts.name,
        kind="",
        start_time_unix_nano=ts.start_time_ns,
        end_time_unix_nano=ts.start_time_ns + ts.duration_ns,
        attributes=dict(ts.attributes),
        status=status,
        events=list(ts.events),
        resource_attributes=dict(ts.resource_attributes),
    )


def _build_provider(config: AppConfig) -> TraceProvider:
    """Instantiate the appropriate TraceProvider based on configuration."""
    if config.provider == "signoz":
        from rf_trace_viewer.providers import SigNozProvider

        signoz_config = SigNozConfig(
            endpoint=config.signoz_endpoint or "",
            api_key=config.signoz_api_key or "",
            execution_attribute=config.execution_attribute,
            poll_interval=config.poll_interval,
            max_spans_per_page=config.max_spans_per_page,
            max_spans=config.max_spans,
            overlap_window_seconds=config.overlap_window_seconds,
            service_name=config.service_name,
            jwt_secret=config.signoz_jwt_secret,
            signoz_user_id=config.signoz_user_id,
            signoz_org_id=config.signoz_org_id,
            signoz_email=config.signoz_email,
        )
        return SigNozProvider(signoz_config)
    else:
        from rf_trace_viewer.providers import JsonProvider

        return JsonProvider(path=config.input_path)


def _run_provider_pipeline(config: AppConfig, report_options: ReportOptions) -> int:
    """Run the provider-based static report pipeline. Returns exit code."""
    from rf_trace_viewer.robot_semantics import RobotSemanticsLayer

    provider = _build_provider(config)
    semantics = RobotSemanticsLayer(execution_attribute=config.execution_attribute)

    # Fetch all spans via provider
    vm = provider.fetch_all()
    vm = semantics.enrich(vm)

    # Convert TraceSpan → RawSpan for existing pipeline
    raw_spans = [_trace_span_to_raw_span(ts) for ts in vm.spans]
    roots = build_tree(raw_spans)
    model = interpret_tree(roots)

    html = generate_report(model, report_options)

    output_path = config.output_path
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    test_count = model.statistics.total_tests
    passed = model.statistics.passed
    failed = model.statistics.failed
    skipped = model.statistics.skipped
    print(
        f"Report generated: {output_path} "
        f"({len(raw_spans)} spans, {test_count} tests: "
        f"{passed} passed, {failed} failed, {skipped} skipped)"
    )
    return 0


def _run_live_server(args: argparse.Namespace) -> int:
    """Start the live HTTP server. Returns exit code."""
    from rf_trace_viewer.server import LiveServer

    try:
        cli_dict = _args_to_cli_dict(args)
        config = load_config(cli_dict, config_path=getattr(args, "config", None))
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    trace_path = config.input_path or ""

    journal_path = None if config.no_journal else config.journal
    report_options = _build_report_options(args, logo_path=config.logo_path)

    # Build provider for non-json modes
    provider = None
    if config.provider != "json":
        provider = _build_provider(config)

    # Build K8s integration objects when clickhouse_host is configured
    health_router = None
    status_poller = None
    rate_limiter = None
    query_semaphore = None
    if config.clickhouse_host:
        from rf_trace_viewer.health import HealthRouter, StatusPoller

        health_router = HealthRouter(
            clickhouse_host=config.clickhouse_host,
            clickhouse_port=config.clickhouse_port,
            health_check_timeout=config.health_check_timeout,
        )
        status_poller = StatusPoller(
            clickhouse_host=config.clickhouse_host,
            clickhouse_port=config.clickhouse_port,
            signoz_endpoint=config.signoz_endpoint,
            signoz_api_key=config.signoz_api_key,
            poll_interval=config.status_poll_interval,
        )
        if config.rate_limit_per_ip:
            from rf_trace_viewer.rate_limit import SlidingWindowRateLimiter

            rate_limiter = SlidingWindowRateLimiter(
                requests_per_minute=config.rate_limit_per_ip,
            )
        if config.max_concurrent_queries:
            import threading

            query_semaphore = threading.Semaphore(config.max_concurrent_queries)

    server = LiveServer(
        trace_path=trace_path,
        port=config.port,
        title=config.title,
        poll_interval=config.poll_interval,
        receiver_mode=config.receiver,
        journal_path=journal_path,
        forward_url=config.forward,
        output_path=config.output_path,
        report_options=report_options,
        provider=provider,
        base_url=config.base_url,
        lookback=config.lookback or getattr(args, "lookback", None),
        max_spans=config.max_spans,
        service_name=config.service_name,
        execution_attribute=config.execution_attribute,
        health_router=health_router,
        status_poller=status_poller,
        rate_limiter=rate_limiter,
        base_filter=config.base_filter,
        query_semaphore=query_semaphore,
        logo_path=config.logo_path,
    )
    server.start(open_browser=not config.no_open)
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

    # Static mode requires an input file (for json provider) or signoz config
    if args.input is None and args.provider != "signoz":
        print(
            "Error: input file is required (or use --receiver, serve, or --provider signoz)",
            file=sys.stderr,
        )
        return 1

    # Static mode pipeline via load_config + provider abstraction
    try:
        cli_dict = _args_to_cli_dict(args)
        config = load_config(cli_dict, config_path=args.config)

        # For json provider, use the direct pipeline for backward compatibility
        # (parse_file → build_tree → interpret_tree → generate_report)
        if config.provider == "json":
            spans = parse_file(config.input_path)
            roots = build_tree(spans)
            model = interpret_tree(roots)

            options = _build_report_options(args, logo_path=config.logo_path)
            html = generate_report(model, options)

            with open(config.output_path, "w", encoding="utf-8") as f:
                f.write(html)

            test_count = model.statistics.total_tests
            passed = model.statistics.passed
            failed = model.statistics.failed
            skipped = model.statistics.skipped
            print(
                f"Report generated: {config.output_path} "
                f"({len(spans)} spans, {test_count} tests: "
                f"{passed} passed, {failed} failed, {skipped} skipped)"
            )
            return 0

        # Non-json providers use the provider pipeline
        report_options = _build_report_options(args, logo_path=config.logo_path)
        return _run_provider_pipeline(config, report_options)

    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
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
