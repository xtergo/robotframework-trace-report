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
from rf_trace_viewer.rf_model import RFRunModel, interpret_tree
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
        default=None,
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
        default=None,
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
        default=None,
        help="Span attribute name for grouping executions (default: execution_id)",
    )
    parser.add_argument(
        "--max-spans-per-page",
        type=int,
        default=None,
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
        default=None,
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
        "--follow-traces",
        action="store_true",
        default=None,
        help="Fetch cross-service spans sharing the same trace_id (default: enabled when --service-name is set)",
    )
    parser.add_argument(
        "--no-follow-traces",
        action="store_true",
        default=False,
        help="Disable cross-service trace following (avoids the second query per poll)",
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
    parser.add_argument(
        "--logs-file",
        default=None,
        metavar="<path>",
        help="Path to a separate NDJSON file containing OTLP log records (resourceLogs)",
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
        "logs_file": "logs_path",
    }
    result = {}
    for arg_name, config_name in mapping.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            result[config_name] = val
    # Handle --follow-traces / --no-follow-traces boolean pair
    if getattr(args, "no_follow_traces", False):
        result["follow_traces"] = False
    elif getattr(args, "follow_traces", None):
        result["follow_traces"] = True
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


def _validate_logs_file(args: argparse.Namespace) -> int | None:
    """Validate --logs-file exists if provided. Returns exit code on error, None on success."""
    logs_file = getattr(args, "logs_file", None)
    if logs_file is not None:
        import os

        if not os.path.exists(logs_file):
            print(f"Error: logs file not found: {logs_file}", file=sys.stderr)
            return 1
    return None


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

        return JsonProvider(path=config.input_path, logs_path=config.logs_path)


def _parse_xml_input(path: str) -> list[RawSpan]:
    """Parse an RF output.xml file by converting it to OTel spans in-memory.

    Uses the existing output_xml_converter to produce an
    ExportTraceServiceRequest dict, then feeds it through parse_line.
    """
    import json
    import xml.etree.ElementTree as ET

    from rf_trace_viewer.output_xml_converter import convert_xml
    from rf_trace_viewer.parser import parse_line

    tree = ET.parse(path)
    root = tree.getroot()
    data = convert_xml(root)
    return parse_line(json.dumps(data))


def _is_xml_input(path: str) -> bool:
    """Detect whether the input file is an RF output.xml."""
    return path.endswith(".xml")


def _attach_log_counts_to_model(
    model: RFRunModel,
    log_count_map: dict[str, int],
    log_severity_map: dict[str, dict[str, int]] | None = None,
) -> None:
    """Walk the model tree and set ``_log_count`` on nodes that have logs.

    Also computes ``_descendant_log_count`` and severity breakdowns on
    parent nodes so the tree row can show per-severity indicators.
    """
    from rf_trace_viewer.rf_model import RFKeyword, RFSuite, RFTest

    if log_severity_map is None:
        log_severity_map = {}

    # First pass: set direct _log_count and _log_severity_counts
    stack: list = list(model.suites)
    while stack:
        node = stack.pop()
        count = log_count_map.get(node.id, 0)
        if count > 0:
            node._log_count = count
        sev = log_severity_map.get(node.id)
        if sev:
            node._log_severity_counts = dict(sev)
        if isinstance(node, RFSuite):
            stack.extend(node.children)
        elif isinstance(node, RFTest):
            stack.extend(node.keywords)
        elif isinstance(node, RFKeyword):
            stack.extend(node.children)

    # Second pass: bubble up descendant log counts (post-order)
    def _bubble(node: RFSuite | RFTest | RFKeyword) -> tuple[int, dict[str, int]]:
        total = node._log_count
        agg_sev: dict[str, int] = {}
        children: list = []
        if isinstance(node, RFSuite):
            children = node.children
        elif isinstance(node, RFTest):
            children = node.keywords
        elif isinstance(node, RFKeyword):
            children = node.children
        for child in children:
            child_total, child_sev = _bubble(child)
            total += child_total
            for k, v in child_sev.items():
                agg_sev[k] = agg_sev.get(k, 0) + v
        node._descendant_log_count = total - node._log_count
        # Descendant severity = aggregated children severity (excludes own)
        node._descendant_log_severity_counts = dict(agg_sev)
        # Return total including own severity for parent aggregation
        own_sev = node._log_severity_counts or {}
        merged: dict[str, int] = dict(agg_sev)
        for k, v in own_sev.items():
            merged[k] = merged.get(k, 0) + v
        return total, merged

    for suite in model.suites:
        _bubble(suite)


def _collect_embedded_logs(provider: TraceProvider) -> dict[str, list[dict]]:
    """Collect all log data from a provider for embedding in static HTML.

    Returns a dict keyed by span_id with lists of log record dicts.
    Only works for providers that have a ``_log_index`` (i.e. JsonProvider).
    """
    log_index = getattr(provider, "_log_index", None)
    if not log_index:
        return {}
    result: dict[str, list[dict]] = {}
    for span_id, records in log_index.items():
        if not records:
            continue
        result[span_id] = provider.get_logs(span_id, "")
    return result


def _run_provider_pipeline(config: AppConfig, report_options: ReportOptions) -> int:
    """Run the provider-based static report pipeline. Returns exit code."""
    from rf_trace_viewer.robot_semantics import RobotSemanticsLayer

    provider = _build_provider(config)
    semantics = RobotSemanticsLayer(execution_attribute=config.execution_attribute)

    # Fetch all spans via provider
    vm = provider.fetch_all()
    vm = semantics.enrich(vm)

    # Build log_count map from TraceSpan._log_count (set by provider)
    log_count_map: dict[str, int] = {}
    log_severity_map: dict[str, dict[str, int]] = {}
    for ts in vm.spans:
        count = getattr(ts, "_log_count", 0)
        if count > 0:
            log_count_map[ts.span_id] = count
        sev = getattr(ts, "_log_severity_counts", None)
        if sev:
            log_severity_map[ts.span_id] = dict(sev)

    # Convert TraceSpan → RawSpan for existing pipeline
    raw_spans = [_trace_span_to_raw_span(ts) for ts in vm.spans]
    roots = build_tree(raw_spans)
    model = interpret_tree(roots)

    # Attach log counts to model nodes
    _attach_log_counts_to_model(model, log_count_map, log_severity_map)

    # Collect embedded log data for static HTML (no server to fetch from)
    embedded_logs = _collect_embedded_logs(provider)

    html = generate_report(model, report_options, embedded_logs=embedded_logs)

    output_path = config.output_path
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    test_count = model.statistics.total_tests
    passed = model.statistics.passed
    failed = model.statistics.failed
    skipped = model.statistics.skipped
    log_msg = f" with {sum(log_count_map.values())} logs" if log_count_map else ""
    print(
        f"Report generated: {output_path} "
        f"({len(raw_spans)} spans, {test_count} tests: "
        f"{passed} passed, {failed} failed, {skipped} skipped{log_msg})"
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
        follow_traces=config.follow_traces,
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


def _is_convert_subcommand() -> bool:
    """Check if the first non-option argument in sys.argv is 'convert'."""
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            continue
        return arg == "convert"
    return False


def _build_convert_parser() -> argparse.ArgumentParser:
    """Build the parser for the 'convert' subcommand."""
    parser = argparse.ArgumentParser(
        prog="rf-trace-report convert",
        description="Convert RF output.xml to OTLP NDJSON trace file",
    )
    parser.add_argument(
        "input",
        help="Path to RF output.xml file",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output NDJSON file path (default: input with .json.gz extension)",
    )
    return parser


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

    # Detect 'convert' subcommand before argparse to avoid positional arg conflict
    if _is_convert_subcommand():
        import os

        parser = _build_convert_parser()
        args = parser.parse_args(sys.argv[2:])
        output_path = args.output or os.path.splitext(args.input)[0] + ".json.gz"
        try:
            from rf_trace_viewer.output_xml_converter import convert_file

            convert_file(args.input, output_path)
            print(output_path)
            return 0
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1

    # Detect 'serve' subcommand before argparse to avoid positional arg conflict
    if _is_serve_subcommand():
        parser = _build_serve_parser()
        # Strip 'serve' from argv before parsing
        args = parser.parse_args(sys.argv[2:])
        args.live = True
        err = _validate_logs_file(args)
        if err is not None:
            return err
        return _run_live_server(args)

    # Default (legacy) parser
    parser = _build_default_parser()
    args = parser.parse_args()

    # Validate --logs-file early
    err = _validate_logs_file(args)
    if err is not None:
        return err

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
        # When --logs-file is provided, use the provider pipeline so logs
        # are parsed and _log_count is attached to spans.
        if config.provider == "json" and not config.logs_path:
            if _is_xml_input(config.input_path):
                print("Detected RF output.xml, converting to OTel format...")
                spans = _parse_xml_input(config.input_path)
            else:
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
