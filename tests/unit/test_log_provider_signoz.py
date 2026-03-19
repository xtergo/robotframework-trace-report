"""Unit tests for SigNoz log query builders (Task 4.1)."""

from __future__ import annotations

from rf_trace_viewer.providers.signoz_provider import SigNozProvider

# ---------------------------------------------------------------------------
# _build_log_count_query â aggregate count query
# ---------------------------------------------------------------------------


class TestBuildLogCountQuery:
    """Verify _build_log_count_query produces correct payload structure."""

    def test_data_source_is_logs(self):
        query = SigNozProvider._build_log_count_query({"trace-1"})
        bq = query["compositeQuery"]["builderQueries"]["A"]
        assert bq["dataSource"] == "logs"

    def test_aggregate_operator_is_count(self):
        query = SigNozProvider._build_log_count_query({"trace-1"})
        bq = query["compositeQuery"]["builderQueries"]["A"]
        assert bq["aggregateOperator"] == "count"

    def test_group_by_span_id(self):
        query = SigNozProvider._build_log_count_query({"trace-1"})
        bq = query["compositeQuery"]["builderQueries"]["A"]
        assert len(bq["groupBy"]) == 1
        assert bq["groupBy"][0]["key"] == "span_id"
        assert bq["groupBy"][0]["isColumn"] is True

    def test_filter_trace_id_in(self):
        trace_ids = {"trace-a", "trace-b", "trace-c"}
        query = SigNozProvider._build_log_count_query(trace_ids)
        bq = query["compositeQuery"]["builderQueries"]["A"]
        items = bq["filters"]["items"]
        assert len(items) == 1
        f = items[0]
        assert f["key"]["key"] == "trace_id"
        assert f["key"]["isColumn"] is True
        assert f["op"] == "in"
        assert set(f["value"]) == trace_ids

    def test_filter_values_sorted(self):
        trace_ids = {"z-trace", "a-trace", "m-trace"}
        query = SigNozProvider._build_log_count_query(trace_ids)
        items = query["compositeQuery"]["builderQueries"]["A"]["filters"]["items"]
        assert items[0]["value"] == sorted(trace_ids)

    def test_panel_type_is_table(self):
        query = SigNozProvider._build_log_count_query({"t1"})
        assert query["compositeQuery"]["panelType"] == "table"

    def test_query_type_is_builder(self):
        query = SigNozProvider._build_log_count_query({"t1"})
        assert query["compositeQuery"]["queryType"] == "builder"

    def test_start_end_timestamps_present(self):
        query = SigNozProvider._build_log_count_query({"t1"})
        assert "start" in query
        assert "end" in query
        assert query["start"] < query["end"]


# ---------------------------------------------------------------------------
# _build_log_query â list query for log records
# ---------------------------------------------------------------------------


class TestBuildLogQuery:
    """Verify _build_log_query produces correct payload structure."""

    def test_data_source_is_logs(self):
        query = SigNozProvider._build_log_query("span-1", "trace-1")
        bq = query["compositeQuery"]["builderQueries"]["A"]
        assert bq["dataSource"] == "logs"

    def test_panel_type_is_list(self):
        query = SigNozProvider._build_log_query("span-1", "trace-1")
        assert query["compositeQuery"]["panelType"] == "list"

    def test_filters_contain_trace_id_and_span_id(self):
        query = SigNozProvider._build_log_query("span-abc", "trace-xyz")
        bq = query["compositeQuery"]["builderQueries"]["A"]
        items = bq["filters"]["items"]
        keys = {item["key"]["key"] for item in items}
        assert keys == {"trace_id", "span_id"}

    def test_trace_id_filter_value(self):
        query = SigNozProvider._build_log_query("s1", "t1")
        items = query["compositeQuery"]["builderQueries"]["A"]["filters"]["items"]
        trace_filter = [i for i in items if i["key"]["key"] == "trace_id"][0]
        assert trace_filter["op"] == "="
        assert trace_filter["value"] == "t1"

    def test_span_id_filter_value(self):
        query = SigNozProvider._build_log_query("s1", "t1")
        items = query["compositeQuery"]["builderQueries"]["A"]["filters"]["items"]
        span_filter = [i for i in items if i["key"]["key"] == "span_id"][0]
        assert span_filter["op"] == "="
        assert span_filter["value"] == "s1"

    def test_select_columns_include_required_fields(self):
        query = SigNozProvider._build_log_query("s1", "t1")
        bq = query["compositeQuery"]["builderQueries"]["A"]
        col_keys = {c["key"] for c in bq["selectColumns"]}
        assert {"timestamp", "severity_text", "body"} <= col_keys

    def test_order_by_timestamp_ascending(self):
        query = SigNozProvider._build_log_query("s1", "t1")
        bq = query["compositeQuery"]["builderQueries"]["A"]
        assert len(bq["orderBy"]) >= 1
        assert bq["orderBy"][0]["columnName"] == "timestamp"
        assert bq["orderBy"][0]["order"] == "asc"

    def test_aggregate_operator_is_noop(self):
        query = SigNozProvider._build_log_query("s1", "t1")
        bq = query["compositeQuery"]["builderQueries"]["A"]
        assert bq["aggregateOperator"] == "noop"

    def test_query_type_is_builder(self):
        query = SigNozProvider._build_log_query("s1", "t1")
        assert query["compositeQuery"]["queryType"] == "builder"

    def test_start_end_timestamps_present(self):
        query = SigNozProvider._build_log_query("s1", "t1")
        assert "start" in query
        assert "end" in query
        assert query["start"] < query["end"]
