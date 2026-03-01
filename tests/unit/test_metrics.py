"""Unit tests for the metrics module."""

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from rf_trace_viewer.metrics import (
    _configure_log_level,
    _DiagnosticsExporter,
    _load_config,
    init_metrics,
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


class TestConfigureLogLevel:
    """Tests for _configure_log_level() -- Req 10.1."""

    def test_info_level(self):
        """'info' maps to logging.INFO."""
        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        _configure_log_level("info")
        assert test_logger.level == logging.INFO

    def test_debug_level(self):
        """'debug' maps to logging.DEBUG."""
        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        _configure_log_level("debug")
        assert test_logger.level == logging.DEBUG

    def test_warn_level(self):
        """'warn' maps to logging.WARNING."""
        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        _configure_log_level("warn")
        assert test_logger.level == logging.WARNING

    def test_case_insensitive(self):
        """Level string is case-insensitive."""
        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        _configure_log_level("DEBUG")
        assert test_logger.level == logging.DEBUG

    def test_unknown_level_defaults_to_info(self, caplog):
        """Unknown level falls back to INFO with a warning."""
        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        with caplog.at_level(logging.WARNING):
            _configure_log_level("verbose")
        assert test_logger.level == logging.INFO
        assert "Unknown TRACE_REPORT_LOG_LEVEL" in caplog.text


class TestDiagnosticsExporter:
    """Tests for _DiagnosticsExporter -- Reqs 10.2, 10.3, 7.2, 7.3."""

    def _make_metrics_data(self, num_points=3):
        """Build a minimal mock MetricsData with *num_points* data points."""
        data_points = [MagicMock() for _ in range(num_points)]
        metric = MagicMock()
        metric.data.data_points = data_points
        scope_metrics = MagicMock()
        scope_metrics.metrics = [metric]
        resource_metrics = MagicMock()
        resource_metrics.scope_metrics = [scope_metrics]
        metrics_data = MagicMock()
        metrics_data.resource_metrics = [resource_metrics]
        return metrics_data

    def test_diagnostics_true_logs_success(self, caplog):
        """When diagnostics=True, successful exports are logged at INFO."""
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = MagicMock()
        inner.export.return_value = MetricExportResult.SUCCESS
        wrapper = _DiagnosticsExporter(inner, diagnostics=True)
        data = self._make_metrics_data(5)

        with caplog.at_level(logging.INFO):
            result = wrapper.export(data)

        assert result == MetricExportResult.SUCCESS
        assert "export succeeded" in caplog.text
        assert "5 data points exported" in caplog.text

    def test_diagnostics_false_no_success_log(self, caplog):
        """When diagnostics=False, successful exports are NOT logged."""
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = MagicMock()
        inner.export.return_value = MetricExportResult.SUCCESS
        wrapper = _DiagnosticsExporter(inner, diagnostics=False)
        data = self._make_metrics_data(5)

        with caplog.at_level(logging.INFO):
            result = wrapper.export(data)

        assert result == MetricExportResult.SUCCESS
        assert "export succeeded" not in caplog.text

    def test_failure_logged_as_warning_diagnostics_true(self, caplog):
        """Export failure is logged as WARNING when diagnostics=True."""
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = MagicMock()
        inner.export.return_value = MetricExportResult.FAILURE
        wrapper = _DiagnosticsExporter(inner, diagnostics=True)
        data = self._make_metrics_data(4)

        with caplog.at_level(logging.WARNING):
            result = wrapper.export(data)

        assert result == MetricExportResult.FAILURE
        assert "export failed" in caplog.text
        assert "4 data points" in caplog.text

    def test_failure_logged_as_warning_diagnostics_false(self, caplog):
        """Export failure is logged as WARNING even when diagnostics=False."""
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = MagicMock()
        inner.export.return_value = MetricExportResult.FAILURE
        wrapper = _DiagnosticsExporter(inner, diagnostics=False)
        data = self._make_metrics_data(2)

        with caplog.at_level(logging.WARNING):
            result = wrapper.export(data)

        assert result == MetricExportResult.FAILURE
        assert "export failed" in caplog.text

    def test_exception_logged_with_reason(self, caplog):
        """When inner exporter raises, the failure reason is logged (Req 7.3)."""
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = MagicMock()
        inner.export.side_effect = ConnectionError("collector unreachable")
        wrapper = _DiagnosticsExporter(inner, diagnostics=False)
        data = self._make_metrics_data(3)

        with caplog.at_level(logging.WARNING):
            result = wrapper.export(data)

        assert result == MetricExportResult.FAILURE
        assert "collector unreachable" in caplog.text
        assert "3 data points" in caplog.text

    def test_shutdown_delegates(self):
        """shutdown() delegates to the inner exporter."""
        inner = MagicMock()
        wrapper = _DiagnosticsExporter(inner)
        wrapper.shutdown(timeout_millis=5000)
        inner.shutdown.assert_called_once_with(timeout_millis=5000)

    def test_force_flush_delegates(self):
        """force_flush() delegates to the inner exporter."""
        inner = MagicMock()
        wrapper = _DiagnosticsExporter(inner)
        wrapper.force_flush(timeout_millis=3000)
        inner.force_flush.assert_called_once_with(timeout_millis=3000)

    def test_count_data_points_empty(self):
        """_count_data_points returns 0 for empty metrics data."""
        data = self._make_metrics_data(0)
        assert _DiagnosticsExporter._count_data_points(data) == 0


class TestInitMetricsLogLevel:
    """Tests that init_metrics configures log level from env var."""

    def test_init_metrics_sets_log_level_debug(self):
        """init_metrics configures logger to DEBUG when LOG_LEVEL=debug."""
        env = {"TRACE_REPORT_LOG_LEVEL": "debug"}
        with patch.dict(os.environ, env, clear=True):
            init_metrics()

        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        assert test_logger.level == logging.DEBUG

    def test_init_metrics_sets_log_level_warn(self):
        """init_metrics configures logger to WARNING when LOG_LEVEL=warn."""
        env = {"TRACE_REPORT_LOG_LEVEL": "warn"}
        with patch.dict(os.environ, env, clear=True):
            init_metrics()

        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        assert test_logger.level == logging.WARNING

    def test_init_metrics_sets_log_level_even_when_disabled(self):
        """Log level is configured even when metrics are disabled."""
        env = {
            "TRACE_REPORT_METRICS_ENABLED": "false",
            "TRACE_REPORT_LOG_LEVEL": "debug",
        }
        with patch.dict(os.environ, env, clear=True):
            init_metrics()

        test_logger = logging.getLogger("rf_trace_viewer.metrics")
        assert test_logger.level == logging.DEBUG
