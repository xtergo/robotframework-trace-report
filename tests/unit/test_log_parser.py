"""Unit tests for OTLP log record parsing."""

import json

import pytest

from rf_trace_viewer.parser import RawLogRecord, parse_log_line


class TestRawLogRecordDataclass:
    """Test RawLogRecord dataclass construction."""

    def test_basic_construction(self):
        record = RawLogRecord(
            trace_id="abc123",
            span_id="def456",
            timestamp_unix_nano=1700000000000000000,
            severity_text="INFO",
            body="hello world",
        )
        assert record.trace_id == "abc123"
        assert record.span_id == "def456"
        assert record.timestamp_unix_nano == 1700000000000000000
        assert record.severity_text == "INFO"
        assert record.body == "hello world"
        assert record.attributes == {}
        assert record.resource_attributes == {}

    def test_with_attributes(self):
        record = RawLogRecord(
            trace_id="abc",
            span_id="def",
            timestamp_unix_nano=0,
            severity_text="ERROR",
            body="fail",
            attributes={"key": "val"},
            resource_attributes={"service.name": "myapp"},
        )
        assert record.attributes == {"key": "val"}
        assert record.resource_attributes == {"service.name": "myapp"}


def _make_resource_logs_line(
    log_records,
    resource_attrs=None,
    use_camel_case=False,
):
    """Helper to build a valid resourceLogs JSON line."""
    if resource_attrs is None:
        resource_attrs = []

    if use_camel_case:
        return json.dumps(
            {
                "resourceLogs": [
                    {
                        "resource": {"attributes": resource_attrs},
                        "scopeLogs": [{"scope": {"name": "test"}, "logRecords": log_records}],
                    }
                ]
            }
        )
    return json.dumps(
        {
            "resourceLogs": [
                {
                    "resource": {"attributes": resource_attrs},
                    "scopeLogs": [{"scope": {"name": "test"}, "logRecords": log_records}],
                }
            ]
        }
    )


def _make_log_record(
    trace_id="abc123",
    span_id="def456",
    timestamp=1700000000000000000,
    severity="INFO",
    body="test message",
    attributes=None,
    use_camel_case=False,
):
    """Helper to build a single OTLP log record dict."""
    if use_camel_case:
        rec = {
            "traceId": trace_id,
            "spanId": span_id,
            "timeUnixNano": str(timestamp),
            "severityText": severity,
            "body": {"stringValue": body},
        }
    else:
        rec = {
            "traceId": trace_id,
            "spanId": span_id,
            "timeUnixNano": str(timestamp),
            "severityText": severity,
            "body": {"stringValue": body},
        }
    if attributes:
        rec["attributes"] = attributes
    return rec


class TestParseLogLine:
    """Test parse_log_line function."""

    def test_single_log_record(self):
        line = _make_resource_logs_line([_make_log_record()])
        records = parse_log_line(line)
        assert len(records) == 1
        assert records[0].trace_id == "abc123"
        assert records[0].span_id == "def456"
        assert records[0].severity_text == "INFO"
        assert records[0].body == "test message"

    def test_multiple_log_records(self):
        log_records = [
            _make_log_record(span_id="aaa", body="first"),
            _make_log_record(span_id="bbb", body="second"),
        ]
        line = _make_resource_logs_line(log_records)
        records = parse_log_line(line)
        assert len(records) == 2
        assert records[0].span_id == "aaa"
        assert records[1].span_id == "bbb"

    def test_skips_record_missing_span_id(self):
        log_records = [
            _make_log_record(span_id="", body="no span"),
            _make_log_record(span_id="valid", body="has span"),
        ]
        line = _make_resource_logs_line(log_records)
        records = parse_log_line(line)
        assert len(records) == 1
        assert records[0].span_id == "valid"

    def test_skips_record_missing_trace_id(self):
        log_records = [
            _make_log_record(trace_id="", body="no trace"),
            _make_log_record(trace_id="valid", body="has trace"),
        ]
        line = _make_resource_logs_line(log_records)
        records = parse_log_line(line)
        assert len(records) == 1
        assert records[0].trace_id == "valid"

    def test_extracts_resource_attributes(self):
        res_attrs = [{"key": "service.name", "value": {"stringValue": "myapp"}}]
        line = _make_resource_logs_line([_make_log_record()], resource_attrs=res_attrs)
        records = parse_log_line(line)
        assert len(records) == 1
        assert records[0].resource_attributes == {"service.name": "myapp"}

    def test_extracts_log_attributes(self):
        attrs = [{"key": "http.method", "value": {"stringValue": "GET"}}]
        line = _make_resource_logs_line([_make_log_record(attributes=attrs)])
        records = parse_log_line(line)
        assert len(records) == 1
        assert records[0].attributes == {"http.method": "GET"}

    def test_normalizes_ids_to_lowercase(self):
        line = _make_resource_logs_line([_make_log_record(trace_id="ABCDEF", span_id="123ABC")])
        records = parse_log_line(line)
        assert records[0].trace_id == "abcdef"
        assert records[0].span_id == "123abc"

    def test_timestamp_parsed_as_int(self):
        line = _make_resource_logs_line([_make_log_record(timestamp=1700000000000000000)])
        records = parse_log_line(line)
        assert records[0].timestamp_unix_nano == 1700000000000000000

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            parse_log_line("not json")

    def test_raises_on_missing_resource_logs(self):
        with pytest.raises(ValueError, match="Missing or invalid resourceLogs"):
            parse_log_line('{"something": "else"}')

    def test_empty_resource_logs(self):
        line = json.dumps({"resourceLogs": []})
        records = parse_log_line(line)
        assert records == []

    def test_body_as_plain_string(self):
        """Handle body as a plain string (not an object)."""
        rec = {
            "traceId": "abc",
            "spanId": "def",
            "timeUnixNano": "1000",
            "severityText": "INFO",
            "body": "plain string body",
        }
        line = json.dumps(
            {
                "resourceLogs": [
                    {
                        "resource": {"attributes": []},
                        "scopeLogs": [{"scope": {}, "logRecords": [rec]}],
                    }
                ]
            }
        )
        records = parse_log_line(line)
        assert len(records) == 1
        assert records[0].body == "plain string body"

    def test_snake_case_keys(self):
        """Handle snake_case OTLP keys (e.g. from Go exporters)."""
        rec = {
            "trace_id": "abc",
            "span_id": "def",
            "time_unix_nano": 5000,
            "severity_text": "WARN",
            "body": {"string_value": "snake case body"},
        }
        line = json.dumps(
            {
                "resource_logs": [
                    {
                        "resource": {"attributes": []},
                        "scope_logs": [{"scope": {}, "log_records": [rec]}],
                    }
                ]
            }
        )
        records = parse_log_line(line)
        assert len(records) == 1
        assert records[0].trace_id == "abc"
        assert records[0].span_id == "def"
        assert records[0].timestamp_unix_nano == 5000
        assert records[0].severity_text == "WARN"
        assert records[0].body == "snake case body"
