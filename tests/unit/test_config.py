"""Tests for the configuration loader: load_config, _load_config_file, _coerce, _to_snake.

Covers three-tier precedence (CLI > config file > env vars), config file
parsing with nested key flattening and camelCase conversion, validation
rules, env var reading, and provider-specific behavior.

Validates: Requirements 46.1, 46.3, 46.8, 46.9, 46.10, 46.11
"""

from __future__ import annotations

import json
import os

import pytest

from rf_trace_viewer.config import (
    AppConfig,
    SigNozConfig,
    _coerce,
    _load_config_file,
    _to_snake,
    load_config,
)
from rf_trace_viewer.providers.base import ConfigurationError

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
SAMPLE_CONFIG = os.path.join(FIXTURES_DIR, "sample_config.json")

# Env vars that load_config reads — cleared in tests that check specific env behavior
_ENV_VARS = [
    "SIGNOZ_ENDPOINT",
    "SIGNOZ_API_KEY",
    "EXECUTION_ATTRIBUTE",
    "POLL_INTERVAL",
    "MAX_SPANS_PER_PAGE",
]


def _clear_env(monkeypatch):
    """Remove all env vars that load_config consults."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ============================================================================
# Section 1: _to_snake helper
# ============================================================================


def test_to_snake_camel_case():
    """Validates: Requirements 46.8 — camelCase to snake_case."""
    assert _to_snake("apiKey") == "api_key"
    assert _to_snake("pollIntervalSeconds") == "poll_interval_seconds"
    assert _to_snake("maxSpansPerPage") == "max_spans_per_page"


def test_to_snake_already_snake():
    """Validates: Requirements 46.8 — already snake_case passes through."""
    assert _to_snake("poll_interval") == "poll_interval"
    assert _to_snake("provider") == "provider"


def test_to_snake_pascal_case():
    """Validates: Requirements 46.8 — PascalCase conversion."""
    assert _to_snake("ExecutionAttribute") == "execution_attribute"


# ============================================================================
# Section 2: _load_config_file
# ============================================================================


def test_load_config_file_sample_fixture():
    """Validates: Requirements 46.8 — nested key flattening and camelCase conversion."""
    result = _load_config_file(SAMPLE_CONFIG)

    # Top-level key preserved
    assert result["provider"] == "signoz"

    # Nested signoz.* keys flattened with prefix and snake_cased
    assert result["signoz_endpoint"] == "https://signoz.example.com"
    assert result["signoz_api_key"] == "your-api-key-here"
    assert result["signoz_execution_attribute"] == "essvt.execution_id"
    assert result["signoz_poll_interval_seconds"] == 5
    assert result["signoz_max_spans_per_page"] == 10000


def test_load_config_file_expected_keys():
    """Validates: Requirements 46.8 — verify exact set of keys from sample fixture."""
    result = _load_config_file(SAMPLE_CONFIG)
    expected_keys = {
        "provider",
        "signoz_endpoint",
        "signoz_api_key",
        "signoz_execution_attribute",
        "signoz_poll_interval_seconds",
        "signoz_max_spans_per_page",
    }
    assert set(result.keys()) == expected_keys


def test_load_config_file_poll_interval_seconds_not_matching_field():
    """Validates: Requirements 46.8 — signoz.pollIntervalSeconds flattens to
    signoz_poll_interval_seconds which does NOT match AppConfig.poll_interval,
    so it should be silently ignored when applied to AppConfig."""
    result = _load_config_file(SAMPLE_CONFIG)
    # The key exists in the flat dict...
    assert "signoz_poll_interval_seconds" in result
    # ...but AppConfig has no such field
    assert not hasattr(AppConfig(), "signoz_poll_interval_seconds")


def test_load_config_file_missing_raises():
    """Validates: Requirements 46.8 — missing config file raises ConfigurationError."""
    with pytest.raises(ConfigurationError, match="Config file not found"):
        _load_config_file("/nonexistent/path/config.json")


def test_load_config_file_invalid_json_raises(tmp_path):
    """Validates: Requirements 46.8 — invalid JSON raises ConfigurationError."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json")
    with pytest.raises(ConfigurationError, match="Cannot parse config file"):
        _load_config_file(str(bad_file))


# ============================================================================
# Section 3: _coerce helper
# ============================================================================


def test_coerce_int():
    """Validates: Requirements 46.11 — int coercion for poll_interval."""
    assert _coerce("poll_interval", "10") == 10
    assert _coerce("max_spans_per_page", "5000") == 5000


def test_coerce_float():
    """Validates: Requirements 46.11 — float coercion for overlap_window_seconds."""
    assert _coerce("overlap_window_seconds", "3.5") == 3.5


def test_coerce_bool():
    """Validates: Requirements 46.11 — bool coercion for live field."""
    assert _coerce("live", "true") is True
    assert _coerce("live", "1") is True
    assert _coerce("live", "yes") is True
    assert _coerce("live", "false") is False
    assert _coerce("live", "0") is False
    assert _coerce("live", "no") is False


def test_coerce_string_passthrough():
    """Validates: Requirements 46.11 — unknown fields pass through as string."""
    assert _coerce("signoz_endpoint", "https://example.com") == "https://example.com"


def test_coerce_invalid_int_raises():
    """Validates: Requirements 46.11 — invalid int raises ConfigurationError."""
    with pytest.raises(ConfigurationError, match="must be an integer"):
        _coerce("poll_interval", "not_a_number")


def test_coerce_invalid_float_raises():
    """Validates: Requirements 46.11 — invalid float raises ConfigurationError."""
    with pytest.raises(ConfigurationError, match="must be a number"):
        _coerce("overlap_window_seconds", "not_a_float")


# ============================================================================
# Section 4: load_config — single source
# ============================================================================


def test_load_config_cli_only(monkeypatch):
    """Validates: Requirements 46.9 — CLI-only args applied correctly."""
    _clear_env(monkeypatch)
    config = load_config({"provider": "json", "title": "My Report"})
    assert config.provider == "json"
    assert config.title == "My Report"


def test_load_config_config_file_only(monkeypatch, tmp_path):
    """Validates: Requirements 46.8 — config file values applied when no CLI args."""
    _clear_env(monkeypatch)
    cfg = {"provider": "signoz", "signoz": {"endpoint": "https://sig.example.com"}}
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))

    config = load_config({}, config_path=str(cfg_file))
    assert config.provider == "signoz"
    assert config.signoz_endpoint == "https://sig.example.com"


def test_load_config_env_var_only(monkeypatch):
    """Validates: Requirements 46.11 — env var read when no CLI or config file."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SIGNOZ_API_KEY", "env-secret-key")
    config = load_config({"provider": "json"})
    assert config.signoz_api_key == "env-secret-key"


# ============================================================================
# Section 5: load_config — precedence
# ============================================================================


def test_cli_overrides_config_file(monkeypatch, tmp_path):
    """Validates: Requirements 46.9 — CLI takes precedence over config file."""
    _clear_env(monkeypatch)
    cfg = {"title": "From Config"}
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))

    config = load_config(
        {"title": "From CLI", "provider": "json"},
        config_path=str(cfg_file),
    )
    assert config.title == "From CLI"


def test_config_file_overrides_env_var(monkeypatch, tmp_path):
    """Validates: Requirements 46.9 — config file takes precedence over env var."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SIGNOZ_ENDPOINT", "https://env.example.com")

    cfg = {
        "provider": "signoz",
        "signoz": {"endpoint": "https://file.example.com"},
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))

    config = load_config({}, config_path=str(cfg_file))
    assert config.signoz_endpoint == "https://file.example.com"


def test_cli_overrides_env_var(monkeypatch):
    """Validates: Requirements 46.9, 46.11 — CLI takes precedence over env var."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SIGNOZ_API_KEY", "env-key")

    config = load_config(
        {"signoz_api_key": "cli-key", "provider": "json"},
    )
    assert config.signoz_api_key == "cli-key"


def test_full_three_tier_precedence(monkeypatch, tmp_path):
    """Validates: Requirements 46.9 — CLI > config file > env var."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SIGNOZ_ENDPOINT", "https://env.example.com")

    cfg = {
        "provider": "signoz",
        "signoz": {"endpoint": "https://file.example.com"},
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))

    config = load_config(
        {"signoz_endpoint": "https://cli.example.com"},
        config_path=str(cfg_file),
    )
    assert config.signoz_endpoint == "https://cli.example.com"


# ============================================================================
# Section 6: Validation
# ============================================================================


def test_signoz_without_endpoint_raises(monkeypatch):
    """Validates: Requirements 46.10 — provider=signoz without endpoint raises."""
    _clear_env(monkeypatch)
    with pytest.raises(ConfigurationError, match="requires --signoz-endpoint"):
        load_config({"provider": "signoz"})


def test_poll_interval_zero_raises(monkeypatch):
    """Validates: Requirements 46.3 — poll_interval=0 is out of range."""
    _clear_env(monkeypatch)
    with pytest.raises(ConfigurationError, match="between 1 and 30"):
        load_config({"provider": "json", "poll_interval": 0})


def test_poll_interval_31_raises(monkeypatch):
    """Validates: Requirements 46.3 — poll_interval=31 is out of range."""
    _clear_env(monkeypatch)
    with pytest.raises(ConfigurationError, match="between 1 and 30"):
        load_config({"provider": "json", "poll_interval": 31})


def test_poll_interval_boundary_low(monkeypatch):
    """Validates: Requirements 46.3 — poll_interval=1 is valid."""
    _clear_env(monkeypatch)
    config = load_config({"provider": "json", "poll_interval": 1})
    assert config.poll_interval == 1


def test_poll_interval_boundary_high(monkeypatch):
    """Validates: Requirements 46.3 — poll_interval=30 is valid."""
    _clear_env(monkeypatch)
    config = load_config({"provider": "json", "poll_interval": 30})
    assert config.poll_interval == 30


# ============================================================================
# Section 7: Provider-specific behavior
# ============================================================================


def test_json_provider_ignores_signoz_validation(monkeypatch):
    """Validates: Requirements 46.1 — provider=json doesn't require signoz endpoint."""
    _clear_env(monkeypatch)
    config = load_config({
        "provider": "json",
        "signoz_endpoint": "https://ignored.example.com",
        "signoz_api_key": "some-key",
    })
    assert config.provider == "json"
    # Values are stored but don't trigger validation errors
    assert config.signoz_endpoint == "https://ignored.example.com"


def test_signoz_api_key_env_var(monkeypatch):
    """Validates: Requirements 46.11 — SIGNOZ_API_KEY env var is read correctly."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SIGNOZ_API_KEY", "my-secret-api-key")
    config = load_config({"provider": "json"})
    assert config.signoz_api_key == "my-secret-api-key"


# ============================================================================
# Section 8: AppConfig defaults
# ============================================================================


def test_app_config_defaults():
    """Validates: Requirements 46.1 — default values match expected defaults."""
    config = AppConfig()
    assert config.provider == "json"
    assert config.input_path is None
    assert config.output_path == "trace-report.html"
    assert config.live is False
    assert config.port == 8077
    assert config.title is None
    assert config.signoz_endpoint is None
    assert config.signoz_api_key is None
    assert config.execution_attribute == "essvt.execution_id"
    assert config.poll_interval == 5
    assert config.max_spans_per_page == 10_000
    assert config.max_spans == 500_000
    assert config.overlap_window_seconds == 2.0
    assert config.receiver is False
    assert config.forward is None
    assert config.journal == "traces.journal.json"
    assert config.no_journal is False
    assert config.no_open is False
    assert config.compact_html is False
    assert config.gzip_embed is False


# ============================================================================
# Section 9: SigNozConfig construction
# ============================================================================


def test_signoz_config_construction():
    """Validates: Requirements 46.3 — SigNozConfig with required fields."""
    cfg = SigNozConfig(
        endpoint="https://signoz.example.com",
        api_key="test-key",
    )
    assert cfg.endpoint == "https://signoz.example.com"
    assert cfg.api_key == "test-key"


def test_signoz_config_defaults():
    """Validates: Requirements 46.3 — SigNozConfig default values."""
    cfg = SigNozConfig(endpoint="https://x.com", api_key="k")
    assert cfg.execution_attribute == "essvt.execution_id"
    assert cfg.poll_interval == 5
    assert cfg.max_spans_per_page == 10_000
    assert cfg.max_spans == 500_000
    assert cfg.overlap_window_seconds == 2.0
