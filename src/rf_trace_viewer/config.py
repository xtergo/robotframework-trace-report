"""Configuration loader with three-tier precedence: CLI > config file > env vars."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from rf_trace_viewer.exceptions import ConfigurationError


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
    execution_attribute: str = "essvt.execution_id"
    poll_interval: int = 5  # seconds (1-30)
    max_spans_per_page: int = 10_000
    max_spans: int = 500_000
    overlap_window_seconds: float = 2.0
    service_name: str | None = None  # filter by service.name in SigNoz queries
    signoz_jwt_secret: str | None = None  # self-hosted JWT secret for auto token refresh
    signoz_user_id: str | None = None  # SigNoz user ID for JWT self-signing
    signoz_org_id: str | None = None  # SigNoz org ID for JWT self-signing
    signoz_email: str | None = None  # SigNoz user email for JWT claims (must match DB)

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


@dataclass
class SigNozConfig:
    """Configuration subset for SigNoz provider construction."""

    endpoint: str  # e.g. "https://signoz.example.com"
    api_key: str  # Bearer token or empty for auto-auth
    execution_attribute: str = "essvt.execution_id"
    poll_interval: int = 5
    max_spans_per_page: int = 10_000
    max_spans: int = 500_000
    overlap_window_seconds: float = 2.0
    service_name: str | None = None  # filter spans by service.name
    jwt_secret: str | None = None  # JWT signing secret for self-hosted auto-auth
    signoz_user_id: str | None = None  # SigNoz user ID for JWT self-signing
    signoz_org_id: str | None = None  # SigNoz org ID for JWT self-signing
    signoz_email: str | None = None  # SigNoz user email for JWT claims


# Fields that hold int values (for env var coercion)
_INT_FIELDS = {"port", "poll_interval", "max_spans_per_page", "max_spans"}
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
