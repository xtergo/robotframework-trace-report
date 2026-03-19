"""Unit tests for JsonProvider log support (task 2.2)."""

import io
import json
import os
import tempfile

from rf_trace_viewer.providers.json_provider import JsonProvider


def _make_span_line(span_id, trace_id="aabb", name="test-span"):
    """Build a minimal resourceSpans NDJSON line."""
    return json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": "test-svc"},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "test"},
                            "spans": [
                                {
                                    "traceId": trace_id,
                                    "spanId": span_id,
                                    "name": name,
                                    "kind": "SPAN_KIND_INTERNAL",
                                    "startTimeUnixNano": "1700000000000000000",
                                    "endTimeUnixNano": "1700000001000000000",
                                    "status": {"code": "STATUS_CODE_OK"},
                                    "attributes": [],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )


def _make_log_line(span_id, trace_id="aabb", body="hello", ts=1700000000000000000, severity="INFO"):
    """Build a minimal resourceLogs NDJSON line."""
    return json.dumps(
        {
            "resourceLogs": [
                {
                    "resource": {"attributes": []},
                    "scopeLogs": [
                        {
                            "scope": {"name": "test"},
                            "logRecords": [
                                {
                                    "traceId": trace_id,
                                    "spanId": span_id,
                                    "timeUnixNano": str(ts),
                                    "severityText": severity,
                                    "body": {"stringValue": body},
                                    "attributes": [
                                        {
                                            "key": "http.method",
                                            "value": {"stringValue": "GET"},
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )


class TestJsonProviderLogsPath:
    """Test logs_path constructor parameter."""

    def test_constructor_accepts_logs_path(self):
        """logs_path is accepted without error."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("")
            f.flush()
            try:
                provider = JsonProvider(stream=io.StringIO(""), logs_path=f.name)
                assert provider._logs_path == f.name
            finally:
                os.unlink(f.name)

    def test_constructor_logs_path_default_none(self):
        provider = JsonProvider(stream=io.StringIO(""))
        assert provider._logs_path is None


class TestJsonProviderLogIndex:
    """Test _log_index building during _parse()."""

    def test_log_index_built_from_embedded_logs(self):
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_log_line("span1", body="log msg 1"),
                _make_log_line("span1", body="log msg 2", ts=1700000000500000000),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()

        assert "span1" in provider._log_index
        assert len(provider._log_index["span1"]) == 2
        # Sorted by timestamp ascending
        assert provider._log_index["span1"][0].body == "log msg 1"
        assert provider._log_index["span1"][1].body == "log msg 2"

    def test_log_index_from_separate_logs_file(self):
        span_content = _make_span_line("span1")
        log_content = _make_log_line("span1", body="separate file log")

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as log_file:
            log_file.write(log_content + "\n")
            log_file.flush()
            try:
                provider = JsonProvider(
                    stream=io.StringIO(span_content),
                    logs_path=log_file.name,
                )
                provider._parse()
                assert "span1" in provider._log_index
                assert len(provider._log_index["span1"]) == 1
            finally:
                os.unlink(log_file.name)

    def test_log_deduplication(self):
        """Logs with same (timestamp, span_id, body) are deduplicated."""
        ts = 1700000000000000000
        log1 = _make_log_line("span1", body="dup msg", ts=ts)
        log2 = _make_log_line("span1", body="dup msg", ts=ts)
        log3 = _make_log_line("span1", body="unique msg", ts=ts)

        content = "\n".join([_make_span_line("span1"), log1, log3])

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as log_file:
            log_file.write(log2 + "\n")
            log_file.flush()
            try:
                provider = JsonProvider(
                    stream=io.StringIO(content),
                    logs_path=log_file.name,
                )
                provider._parse()
                # "dup msg" appears in both sources but should be deduped
                assert len(provider._log_index["span1"]) == 2
            finally:
                os.unlink(log_file.name)

    def test_log_index_empty_when_no_logs(self):
        content = _make_span_line("span1")
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()
        assert provider._log_index == {}

    def test_log_index_multiple_spans(self):
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_span_line("span2"),
                _make_log_line("span1", body="log for span1"),
                _make_log_line("span2", body="log for span2"),
                _make_log_line("span2", body="another for span2", ts=1700000001000000000),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()

        assert len(provider._log_index["span1"]) == 1
        assert len(provider._log_index["span2"]) == 2


class TestJsonProviderLogCount:
    """Test _log_count attachment to spans."""

    def test_log_count_attached_to_spans_with_logs(self):
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_log_line("span1", body="msg1"),
                _make_log_line("span1", body="msg2", ts=1700000000500000000),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        vm = provider.fetch_all()

        span = vm.spans[0]
        assert hasattr(span, "_log_count")
        assert span._log_count == 2  # type: ignore[attr-defined]

    def test_no_log_count_on_spans_without_logs(self):
        content = _make_span_line("span1")
        provider = JsonProvider(stream=io.StringIO(content))
        vm = provider.fetch_all()

        span = vm.spans[0]
        assert not hasattr(span, "_log_count") or span._log_count == 0

    def test_log_count_via_fetch_spans(self):
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_log_line("span1", body="msg"),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        vm, _ = provider.fetch_spans()

        span = vm.spans[0]
        assert hasattr(span, "_log_count")
        assert span._log_count == 1  # type: ignore[attr-defined]


class TestJsonProviderGetLogs:
    """Test get_logs method."""

    def test_get_logs_returns_sorted_dicts(self):
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_log_line("span1", body="second", ts=1700000001000000000),
                _make_log_line("span1", body="first", ts=1700000000000000000),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()

        logs = provider.get_logs("span1", "aabb")
        assert len(logs) == 2
        # Sorted by timestamp ascending
        assert logs[0]["body"] == "first"
        assert logs[1]["body"] == "second"

    def test_get_logs_dict_format(self):
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_log_line(
                    "span1",
                    body="test body",
                    severity="ERROR",
                    ts=1700000000000000000,
                ),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()

        logs = provider.get_logs("span1", "aabb")
        assert len(logs) == 1
        log = logs[0]

        assert "timestamp" in log
        assert "severity" in log
        assert "body" in log
        assert "attributes" in log

        assert log["severity"] == "ERROR"
        assert log["body"] == "test body"
        assert isinstance(log["attributes"], dict)
        assert log["attributes"]["http.method"] == "GET"

    def test_get_logs_timestamp_is_iso8601(self):
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_log_line("span1", ts=1700000000000000000),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()

        logs = provider.get_logs("span1", "aabb")
        ts = logs[0]["timestamp"]
        # Should be a valid ISO 8601 string
        assert "T" in ts
        assert "2023-11-14" in ts

    def test_get_logs_empty_for_unknown_span(self):
        content = _make_span_line("span1")
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()

        logs = provider.get_logs("nonexistent", "aabb")
        assert logs == []

    def test_get_logs_no_external_calls(self):
        """get_logs serves from in-memory index, no HTTP calls."""
        content = "\n".join(
            [
                _make_span_line("span1"),
                _make_log_line("span1", body="offline log"),
            ]
        )
        provider = JsonProvider(stream=io.StringIO(content))
        provider._parse()

        # This should work without any network — purely in-memory
        logs = provider.get_logs("span1", "aabb")
        assert len(logs) == 1
        assert logs[0]["body"] == "offline log"


class TestJsonProviderBackwardCompat:
    """Ensure existing behavior is preserved."""

    def test_fetch_all_still_works_without_logs(self):
        fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
        provider = JsonProvider(path=os.path.join(fixtures, "simple_trace.json"))
        vm = provider.fetch_all()
        assert len(vm.spans) == 4

    def test_list_executions_still_works(self):
        fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
        provider = JsonProvider(path=os.path.join(fixtures, "simple_trace.json"))
        execs = provider.list_executions()
        assert len(execs) == 1
        assert execs[0].span_count == 4
