"""Configuration loader with three-tier precedence: CLI > config file > env vars."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field

from rf_trace_viewer.exceptions import ConfigurationError


@dataclass
class BaseFilterConfig:
    """Server-side service filtering configuration.

    Services in *excluded_by_default* are omitted from query results
    unless the client explicitly includes them.  Services in
    *hard_blocked* can never be queried.
    """

    excluded_by_default: list[str] = field(default_factory=list)
    hard_blocked: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    """Merged configuration from all sources."""

    # Provider selection
    provider: str = "json"  # "json" | "signoz"

    # JSON provider settings (existing)
    input_path: str | None = None
    output_path: str = "trace-report.html"
    live: bool = False
    port: int = 8077
    title: str | None = None

    # SigNoz provider settings
    signoz_endpoint: str | None = None
    signoz_api_key: str | None = None
    execution_attribute: str = "execution_id"
    poll_interval: int = 5  # seconds (1-30)
    max_spans_per_page: int = 10_000
    max_spans: int = 500_000
    overlap_window_seconds: float = 2.0
    service_name: str | None = None  # filter by service.name in SigNoz queries
    signoz_jwt_secret: str | None = None  # self-hosted JWT secret for auto token refresh
    signoz_user_id: str | None = None  # SigNoz user ID for JWT self-signing
    signoz_org_id: str | None = None  # SigNoz org ID for JWT self-signing
    signoz_email: str | None = None  # SigNoz user email for JWT claims (must match DB)
    follow_traces: bool = True  # fetch cross-service spans sharing the same trace_id

    # Existing settings preserved
    receiver: bool = False
    forward: str | None = None
    journal: str = "traces.journal.json"
    no_journal: bool = False
    no_open: bool = False
    compact_html: bool = False
    gzip_embed: bool = False
    base_url: str | None = None
    lookback: str | None = None  # e.g. "10m", "1h", "30s" — only fetch recent spans in live mode
    logo_path: str | None = None  # path to custom SVG logo file

    # K8s deployment settings
    log_format: str = "text"  # "text" | "json"
    status_poll_interval: int = 30  # seconds (5-120)
    health_check_timeout: int = 2  # seconds
    clickhouse_host: str | None = None
    clickhouse_port: int = 8123
    max_concurrent_queries: int | None = None
    base_filter_config: str | None = None  # JSON string or file path
    rate_limit_per_ip: int | None = None  # requests per minute per IP

    # Parsed base filter (populated by load_base_filter)
    _base_filter: BaseFilterConfig = field(default_factory=BaseFilterConfig)

    @property
    def base_filter(self) -> BaseFilterConfig:
        """Return the parsed base filter configuration."""
        return self._base_filter

    @base_filter.setter
    def base_filter(self, value: BaseFilterConfig) -> None:
        self._base_filter = value


@dataclass
class SigNozConfig:
    """Configuration subset for SigNoz provider construction."""

    endpoint: str  # e.g. "https://signoz.example.com"
    api_key: str  # Bearer token or empty for auto-auth
    execution_attribute: str = "execution_id"
    poll_interval: int = 5
    max_spans_per_page: int = 10_000
    max_spans: int = 500_000
    overlap_window_seconds: float = 2.0
    service_name: str | None = None  # filter spans by service.name
    jwt_secret: str | None = None  # JWT signing secret for self-hosted auto-auth
    signoz_user_id: str | None = None  # SigNoz user ID for JWT self-signing
    signoz_org_id: str | None = None  # SigNoz org ID for JWT self-signing
    signoz_email: str | None = None  # SigNoz user email for JWT claims
    follow_traces: bool = True  # fetch cross-service spans sharing the same trace_id


# Fields that hold int values (for env var coercion)
_INT_FIELDS = {
    "port",
    "poll_interval",
    "max_spans_per_page",
    "max_spans",
    "status_poll_interval",
    "health_check_timeout",
    "clickhouse_port",
    "max_concurrent_queries",
    "rate_limit_per_ip",
}
# Fields that hold float values
_FLOAT_FIELDS = {"overlap_window_seconds"}
# Fields that hold bool values
_BOOL_FIELDS = {
    "live",
    "receiver",
    "no_journal",
    "no_open",
    "compact_html",
    "gzip_embed",
    "follow_traces",
}


def _coerce(attr: str, val: str) -> int | float | bool | str:
    """Convert a string env-var value to the type expected by *attr*."""
    if attr in _INT_FIELDS:
        try:
            return int(val)
        except ValueError:
            raise ConfigurationError(
                f"Environment variable for '{attr}' must be an integer, got '{val}'"
            ) from None
    if attr in _FLOAT_FIELDS:
        try:
            return float(val)
        except ValueError:
            raise ConfigurationError(
                f"Environment variable for '{attr}' must be a number, got '{val}'"
            ) from None
    if attr in _BOOL_FIELDS:
        return val.lower() in ("1", "true", "yes")
    return val


_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


def _to_snake(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case."""
    return _CAMEL_RE.sub(r"\1_\2", name).lower()


def _load_config_file(path: str) -> dict:
    """Load a JSON config file and return a flat dict with snake_case keys.

    Nested dicts (e.g. ``signoz.*``) are flattened:
    ``{"signoz": {"apiKey": "x"}}`` → ``{"signoz_api_key": "x"}``.
    """
    if not os.path.exists(path):
        raise ConfigurationError(f"Config file not found: {path}")
    try:
        with open(path) as f:
            raw = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigurationError(f"Cannot parse config file {path}: {exc}") from exc

    flat: dict = {}
    for key, val in raw.items():
        if isinstance(val, dict):
            for subkey, subval in val.items():
                flat_key = f"{key}_{subkey}"
                flat[_to_snake(flat_key)] = subval
        else:
            flat[_to_snake(key)] = val
    return flat


def load_base_filter(config_value: str | None) -> BaseFilterConfig:
    """Parse ``BASE_FILTER_CONFIG`` into a :class:`BaseFilterConfig`.

    *config_value* may be:
    - ``None`` → empty filter (no exclusions)
    - A JSON string (starts with ``{``)
    - A file path pointing to a JSON file

    Expected JSON shape::

        {
            "excluded_by_default": ["svc-a", "svc-b"],
            "hard_blocked": ["svc-x"]
        }

    Raises :class:`ConfigurationError` on parse failure.
    """
    if not config_value:
        return BaseFilterConfig()

    raw_json: str
    if config_value.lstrip().startswith("{"):
        raw_json = config_value
    else:
        # Treat as file path
        if not os.path.exists(config_value):
            raise ConfigurationError(f"BASE_FILTER_CONFIG file not found: {config_value}")
        try:
            with open(config_value) as f:
                raw_json = f.read()
        except OSError as exc:
            raise ConfigurationError(
                f"Cannot read BASE_FILTER_CONFIG file {config_value}: {exc}"
            ) from exc

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Cannot parse BASE_FILTER_CONFIG as JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            "BASE_FILTER_CONFIG must be a JSON object, " f"got {type(data).__name__}"
        )

    return BaseFilterConfig(
        excluded_by_default=list(data.get("excluded_by_default", [])),
        hard_blocked=list(data.get("hard_blocked", [])),
    )


def _validate(config: AppConfig) -> None:
    """Validate the merged configuration, raising ConfigurationError on problems."""
    if config.provider == "signoz" and not config.signoz_endpoint:
        raise ConfigurationError(
            "--provider signoz requires --signoz-endpoint "
            "(via CLI, config file, or SIGNOZ_ENDPOINT env var)"
        )
    if not 1 <= config.poll_interval <= 30:
        raise ConfigurationError(
            f"--poll-interval must be between 1 and 30, got {config.poll_interval}"
        )
    # K8s status poll interval validation
    if not 5 <= config.status_poll_interval <= 120:
        raise ConfigurationError(
            f"STATUS_POLL_INTERVAL must be between 5 and 120, " f"got {config.status_poll_interval}"
        )
    # Parse base filter config (JSON string or file path)
    config.base_filter = load_base_filter(config.base_filter_config)


def validate_svg(path: str) -> tuple[bool, str]:
    """Check that *path* exists and contains an ``<svg`` tag.

    Returns ``(True, "")`` on success, ``(False, reason)`` on failure.
    """
    if not os.path.isfile(path):
        return False, f"File not found: {path}"
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
    except Exception as exc:  # noqa: BLE001
        return False, f"Cannot read file: {path} ({exc})"
    if "<svg" not in content.lower():
        return False, f"Not a valid SVG: {path} (no <svg tag found)"
    return True, ""


def validate_k8s_startup(config: AppConfig) -> None:
    """Fail-fast validation for K8s deployment mode.

    Called at server startup when ``clickhouse_host`` is configured.
    Exits with code 1 and a log message when required secrets are
    missing or configuration is invalid.

    This function does NOT raise — it prints to stderr and calls
    ``sys.exit(1)`` directly so the pod fails visibly.
    """
    if not config.clickhouse_host:
        return  # Not in K8s mode — skip K8s-specific checks

    errors: list[str] = []

    # Required: SigNoz API key or JWT secret for authentication
    if not config.signoz_api_key and not config.signoz_jwt_secret:
        errors.append("K8s mode requires SIGNOZ_API_KEY or SIGNOZ_JWT_SECRET")

    # Validate base filter if configured
    try:
        config.base_filter = load_base_filter(config.base_filter_config)
    except ConfigurationError as exc:
        errors.append(str(exc))

    if errors:
        for msg in errors:
            print(f"FATAL: {msg}", file=sys.stderr)
        sys.exit(1)


def load_config(cli_args: dict, config_path: str | None = None) -> AppConfig:
    """Build an ``AppConfig`` with three-tier precedence.

    Priority (highest → lowest): CLI args → config file → environment variables.
    """
    config = AppConfig()

    # Layer 1: Environment variables (lowest precedence)
    env_map = {
        "SIGNOZ_ENDPOINT": "signoz_endpoint",
        "SIGNOZ_API_KEY": "signoz_api_key",
        "SIGNOZ_JWT_SECRET": "signoz_jwt_secret",
        "SIGNOZ_USER_ID": "signoz_user_id",
        "SIGNOZ_ORG_ID": "signoz_org_id",
        "SIGNOZ_EMAIL": "signoz_email",
        "EXECUTION_ATTRIBUTE": "execution_attribute",
        "POLL_INTERVAL": "poll_interval",
        "MAX_SPANS_PER_PAGE": "max_spans_per_page",
        # K8s environment variables
        "LOG_FORMAT": "log_format",
        "STATUS_POLL_INTERVAL": "status_poll_interval",
        "HEALTH_CHECK_TIMEOUT": "health_check_timeout",
        "CLICKHOUSE_HOST": "clickhouse_host",
        "CLICKHOUSE_PORT": "clickhouse_port",
        "MAX_CONCURRENT_QUERIES": "max_concurrent_queries",
        "BASE_FILTER_CONFIG": "base_filter_config",
        "RATE_LIMIT_PER_IP": "rate_limit_per_ip",
        "LOGO_PATH": "logo_path",
        "FOLLOW_TRACES": "follow_traces",
    }
    for env_key, attr in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            setattr(config, attr, _coerce(attr, val))

    # Layer 2: Config file (middle precedence)
    if config_path:
        file_config = _load_config_file(config_path)
        for key, val in file_config.items():
            if hasattr(config, key) and val is not None:
                setattr(config, key, val)

    # Layer 3: CLI arguments (highest precedence)
    for key, val in cli_args.items():
        if val is not None and hasattr(config, key):
            setattr(config, key, val)

    _validate(config)
    return config
