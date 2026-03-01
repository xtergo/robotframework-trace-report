"""Unit tests for the metrics module."""

import logging
import os
from unittest.mock import patch

import pytest

from rf_trace_viewer.metrics import (
    MetricsConfig,
    _load_config,
    init_metrics,
    shutdown_metrics,
    record_request_start,
    record_request_end,
    record_dep_call,
    record_dep_timeout,
    record_items_returned,
)


class TestLoadConfig:
    """Tests for _load_config() environment variable parsing."""

    def test_defaults_when_no_env_vars(self):
        """All fields use documented defaults when no env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            cfg = _load_config()
        assert cfg.enabled is False
        assert cfg.export_interval_ms == 15_000
        assert cfg.otlp_endpoint is None
        assert cfg.otlp_protocol == "grpc"
        assert cfg.otlp_timeout_s == 5
        assert cfg.otlp_headers is None
        assert cfg.max_queue == 2048
        assert cfg.batch_size == 512
        assert cfg.drop_policy == "drop_oldest"
        assert cfg.diagnostics is False
        assert cfg.log_level == "info"
        assert cfg.attr_allowlist is None

    def test_enabled_true(self):
        with patch.dict(os.environ, {"TRACE_REPORT_METRICS_ENABLED": "true"}, clear=True):
            cfg = _load_config()
        assert cfg.enabled is True

    def test_enabled_case_insensitive(self):
        with patch.dict(os.environ, {"TRACE_REPORT_METRICS_ENABLED": "True"}, clear=True):
            cfg = _load_config()
        assert cfg.enabled is True

    def test_enabled_invalid_treated_as_false(self):
        with patch.dict(os.environ, {"TRACE_REPORT_METRICS_ENABLED": "yes"}, clear=True):
            cfg = _load_config()
        assert cfg.enabled is False

    def test_metrics_endpoint_precedence(self):
        """OTEL_EXPORTER_OTLP_METRICS_ENDPOINT takes precedence."""
        env = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4317",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://metrics:4317",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.otlp_endpoint == "http://metrics:4317"

    def test_generic_endpoint_fallback(self):
        """Falls back to OTEL_EXPORTER_OTLP_ENDPOINT when metrics-specific is unset."""
        env = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4317"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.otlp_endpoint == "http://generic:4317"

    def test_export_interval_custom(self):
        env = {"TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS": "5000"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.export_interval_ms == 5000

    def test_export_interval_non_positive_falls_back(self, caplog):
        env = {"TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS": "0"}
        with patch.dict(os.environ, env, clear=True):
            with caplog.at_level(logging.WARNING):
                cfg = _load_config()
        assert cfg.export_interval_ms == 15_000
        assert "Non-positive" in caplog.text

    def test_export_interval_negative_falls_back(self, caplog):
        env = {"TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS": "-100"}
        with patch.dict(os.environ, env, clear=True):
            with caplog.at_level(logging.WARNING):
                cfg = _load_config()
        assert cfg.export_interval_ms == 15_000
        assert "Non-positive" in caplog.text

    def test_export_interval_below_1000_accepted_with_warning(self, caplog):
        env = {"TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS": "500"}
        with patch.dict(os.environ, env, clear=True):
            with caplog.at_level(logging.WARNING):
                cfg = _load_config()
        assert cfg.export_interval_ms == 500
        assert "below 1000" in caplog.text

    def test_export_interval_invalid_string_falls_back(self, caplog):
        env = {"TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS": "abc"}
        with patch.dict(os.environ, env, clear=True):
            with caplog.at_level(logging.WARNING):
                cfg = _load_config()
        assert cfg.export_interval_ms == 15_000
        assert "Invalid TRACE_REPORT_METRICS_EXPORT_INTERVAL_MS" in caplog.text

    def test_drop_policy_valid_drop_newest(self):
        env = {"TRACE_REPORT_OTEL_DROP_POLICY": "drop_newest"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.drop_policy == "drop_newest"

    def test_drop_policy_invalid_falls_back(self, caplog):
        env = {"TRACE_REPORT_OTEL_DROP_POLICY": "discard"}
        with patch.dict(os.environ, env, clear=True):
            with caplog.at_level(logging.WARNING):
                cfg = _load_config()
        assert cfg.drop_policy == "drop_oldest"
        assert "Invalid TRACE_REPORT_OTEL_DROP_POLICY" in caplog.text

    def test_protocol_http_protobuf(self):
        env = {"OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.otlp_protocol == "http/protobuf"

    def test_protocol_invalid_falls_back(self, caplog):
        env = {"OTEL_EXPORTER_OTLP_PROTOCOL": "json"}
        with patch.dict(os.environ, env, clear=True):
            with caplog.at_level(logging.WARNING):
                cfg = _load_config()
        assert cfg.otlp_protocol == "grpc"
        assert "Invalid OTEL_EXPORTER_OTLP_PROTOCOL" in caplog.text

    def test_otlp_headers_parsed(self):
        env = {"OTEL_EXPORTER_OTLP_HEADERS": "key1=val1,key2=val2"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.otlp_headers == {"key1": "val1", "key2": "val2"}

    def test_attr_allowlist_parsed(self):
        env = {"TRACE_REPORT_METRICS_ATTR_ALLOWLIST": "route,method,status_class"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.attr_allowlist == frozenset({"route", "method", "status_class"})

    def test_attr_allowlist_empty_is_none(self):
        env = {"TRACE_REPORT_METRICS_ATTR_ALLOWLIST": ""}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.attr_allowlist is None

    def test_diagnostics_enabled(self):
        env = {"TRACE_REPORT_OTEL_DIAGNOSTICS": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.diagnostics is True

    def test_custom_log_level(self):
        env = {"TRACE_REPORT_LOG_LEVEL": "debug"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.log_level == "debug"

    def test_timeout_custom(self):
        env = {"OTEL_EXPORTER_OTLP_TIMEOUT": "10"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.otlp_timeout_s == 10

    def test_max_queue_custom(self):
        env = {"TRACE_REPORT_OTEL_MAX_QUEUE": "4096"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.max_queue == 4096

    def test_batch_size_custom(self):
        env = {"TRACE_REPORT_OTEL_BATCH_SIZE": "1024"}
        with patch.dict(os.environ, env, clear=True):
            cfg = _load_config()
        assert cfg.batch_size == 1024

    def test_config_is_frozen(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = _load_config()
        with pytest.raises(AttributeError):
            cfg.enabled = True  # type: ignore[misc]
