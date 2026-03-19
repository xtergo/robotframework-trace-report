"""Unit tests for SigNoz log fetchers and poll_new_spans log attachment (Task 4.2)."""

from __future__ import annotations

from unittest.mock import patch
from urllib.error import URLError

import pytest

from rf_trace_viewer.config import SigNozConfig
from rf_trace_viewer.providers.base import ProviderError
from rf_trace_viewer.providers.signoz_provider import SigNozProvider


def _make_config(**kwargs) -> SigNozConfig:
    defaults = {
        "endpoint": "https://signoz.example.com",
        "api_key": "test-key",
        "execution_attribute": "execution_id",
        "max_spans_per_page": 10_000,
        "overlap_window_seconds": 2.0,
    }
    defaults.update(kwargs)
    return SigNozConfig(**defaults)


def _make_span_response(span_ids: list[str], trace_id: str = "trace001") -> dict:
    """Build a minimal SigNoz query_range response with the given span IDs."""
    rows = [
        {
            "timestamp": "1700000000000000000",
            "data": {
                "spanID": sid,
                "traceID": trace_id,
                "parentSpanID": "",
                "name": f"span-{sid}",
                "durationNano": "1000000",
                "statusCode": "1",
            },
        }
        for sid in span_ids
    ]
    return {"result": [{"list": rows}]}


def _make_log_count_response(counts: dict[str, int | dict[str, int]]) -> dict:
    """Build a SigNoz aggregate response for log counts (table format).

    ``counts`` can be either ``{span_id: total}`` (legacy) or
    ``{span_id: {severity: count}}`` (new severity-grouped format).
    """
    series_list = []
    for span_id, value in counts.items():
        if isinstance(value, dict):
            # severity-grouped: one series entry per (span_id, severity)
            for severity, count in value.items():
                series_list.append(
                    {
                        "labels": {"span_id": span_id, "severity_text": severity},
                        "values": [{"timestamp": 0, "value": str(count)}],
                    }
                )
        else:
            # Legacy: single count, use UNSPECIFIED severity
            series_list.append(
                {
                    "labels": {"span_id": span_id, "severity_text": "UNSPECIFIED"},
                    "values": [{"timestamp": 0, "value": str(value)}],
                }
            )
    return {"data": {"result": [{"queryName": "A", "series": series_list}]}}


def _make_log_list_response(logs: list[dict]) -> dict:
    """Build a SigNoz list response for log records."""
    rows = []
    for log in logs:
        rows.append(
            {
                "timestamp": log.get("timestamp", "1700000000000000000"),
                "data": {
                    "timestamp": log.get("timestamp", "1700000000000000000"),
                    "severity_text": log.get("severity_text", "INFO"),
                    "body": log.get("body", ""),
                    **log.get("extra", {}),
                },
            }
        )
    return {"result": [{"list": rows}]}


# ---------------------------------------------------------------------------
# _fetch_log_counts — success path
# ---------------------------------------------------------------------------


class TestFetchLogCountsSuccess:
    """Verify _fetch_log_counts returns correct span_id -> {severity: count} mapping."""

    def test_returns_counts_from_aggregate_response(self):
        provider = SigNozProvider(_make_config())
        response = _make_log_count_response(
            {
                "span-a": {"INFO": 2, "ERROR": 1},
                "span-b": {"WARN": 1},
            }
        )
        with patch.object(provider, "_api_request", return_value=response):
            result = provider._fetch_log_counts({"trace-1"})
        assert result == {
            "span-a": {"INFO": 2, "ERROR": 1},
            "span-b": {"WARN": 1},
        }

    def test_empty_trace_ids_returns_empty(self):
        provider = SigNozProvider(_make_config())
        result = provider._fetch_log_counts(set())
        assert result == {}

    def test_skips_zero_count_entries(self):
        provider = SigNozProvider(_make_config())
        response = _make_log_count_response(
            {
                "span-a": {"INFO": 5},
                "span-b": {"INFO": 0},
            }
        )
        with patch.object(provider, "_api_request", return_value=response):
            result = provider._fetch_log_counts({"trace-1"})
        assert "span-a" in result
        assert result["span-a"] == {"INFO": 5}
        assert "span-b" not in result


# ---------------------------------------------------------------------------
# _fetch_log_counts — failure paths
# ---------------------------------------------------------------------------


class TestFetchLogCountsFailure:
    """Verify _fetch_log_counts returns {} on any exception."""

    def test_provider_error_returns_empty(self):
        provider = SigNozProvider(_make_config())
        with patch.object(provider, "_api_request", side_effect=ProviderError("err")):
            assert provider._fetch_log_counts({"trace-1"}) == {}

    def test_url_error_returns_empty(self):
        provider = SigNozProvider(_make_config())
        with patch.object(provider, "_api_request", side_effect=URLError("refused")):
            assert provider._fetch_log_counts({"trace-1"}) == {}

    def test_timeout_error_returns_empty(self):
        provider = SigNozProvider(_make_config())
        with patch.object(provider, "_api_request", side_effect=TimeoutError("t/o")):
            assert provider._fetch_log_counts({"trace-1"}) == {}

    def test_generic_exception_returns_empty(self):
        provider = SigNozProvider(_make_config())
        with patch.object(provider, "_api_request", side_effect=RuntimeError("bad")):
            assert provider._fetch_log_counts({"trace-1"}) == {}


# ---------------------------------------------------------------------------
# _fetch_log_counts — 5-second timeout
# ---------------------------------------------------------------------------


class TestFetchLogCountsTimeout:
    """Verify _fetch_log_counts uses timeout=5."""

    def test_uses_5_second_timeout(self):
        provider = SigNozProvider(_make_config())
        response = _make_log_count_response({})
        with patch.object(provider, "_api_request", return_value=response) as mock_req:
            provider._fetch_log_counts({"trace-1"})
        _, kwargs = mock_req.call_args
        assert kwargs.get("timeout") == 5


# ---------------------------------------------------------------------------
# get_logs — success path
# ---------------------------------------------------------------------------


class TestGetLogsSuccess:
    """Verify get_logs returns correctly formatted log records."""

    def test_returns_log_records(self):
        provider = SigNozProvider(_make_config())
        response = _make_log_list_response(
            [
                {
                    "timestamp": "1700000000000000000",
                    "severity_text": "INFO",
                    "body": "started",
                },
                {
                    "timestamp": "1700000001000000000",
                    "severity_text": "ERROR",
                    "body": "failed",
                },
            ]
        )
        with patch.object(provider, "_api_request", return_value=response):
            logs = provider.get_logs("span-1", "trace-1")
        assert len(logs) == 2
        assert logs[0]["severity"] == "INFO"
        assert logs[0]["body"] == "started"
        assert "timestamp" in logs[0]
        assert isinstance(logs[0]["attributes"], dict)
        assert logs[1]["severity"] == "ERROR"

    def test_empty_response_returns_empty_list(self):
        provider = SigNozProvider(_make_config())
        response = {"result": [{"list": []}]}
        with patch.object(provider, "_api_request", return_value=response):
            assert provider.get_logs("span-1", "trace-1") == []


# ---------------------------------------------------------------------------
# get_logs — failure path
# ---------------------------------------------------------------------------


class TestGetLogsFailure:
    """Verify get_logs propagates exceptions (server handles 502)."""

    def test_provider_error_propagates(self):
        provider = SigNozProvider(_make_config())
        with patch.object(provider, "_api_request", side_effect=ProviderError("err")):
            with pytest.raises(ProviderError):
                provider.get_logs("span-1", "trace-1")


# ---------------------------------------------------------------------------
# poll_new_spans — _log_count attachment
# ---------------------------------------------------------------------------


class TestPollNewSpansLogCount:
    """Verify poll_new_spans attaches _log_count from aggregate query."""

    def test_attaches_log_count_to_matching_spans(self):
        provider = SigNozProvider(_make_config())
        span_resp = _make_span_response(["s1", "s2", "s3"])
        log_resp = _make_log_count_response({"s1": 5, "s3": 2})
        call_count = 0

        def fake_api(path, payload, **kwargs):
            nonlocal call_count
            call_count += 1
            return span_resp if call_count == 1 else log_resp

        with patch.object(provider, "_api_request", side_effect=fake_api):
            vm = provider.poll_new_spans(since_ns=1_000_000_000)
        by_id = {s.span_id: s for s in vm.spans}
        assert by_id["s1"]._log_count == 5
        assert by_id["s3"]._log_count == 2
        assert by_id["s2"]._log_count == 0

    def test_no_log_count_when_aggregate_fails(self):
        provider = SigNozProvider(_make_config())
        span_resp = _make_span_response(["s1", "s2"])
        call_count = 0

        def fake_api(path, payload, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return span_resp
            raise ProviderError("timeout")

        with patch.object(provider, "_api_request", side_effect=fake_api):
            vm = provider.poll_new_spans(since_ns=1_000_000_000)
        for span in vm.spans:
            assert span._log_count == 0

    def test_no_log_count_query_when_no_spans(self):
        provider = SigNozProvider(_make_config())
        empty_resp = _make_span_response([])
        with patch.object(provider, "_api_request", return_value=empty_resp) as mock_req:
            vm = provider.poll_new_spans(since_ns=1_000_000_000)
        assert len(vm.spans) == 0
        assert mock_req.call_count == 1
