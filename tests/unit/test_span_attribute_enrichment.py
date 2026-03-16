"""
Property-based and unit tests for span attribute enrichment in the flow table.

This module contains Python mirror functions that replicate the JavaScript logic
from flow-table.js (extractSpanAttributes, generateContextLine, status code
classification, context line truncation), plus Hypothesis strategies for
generating attribute dicts and summary objects.

**Feature: span-attribute-enrichment**
"""

from hypothesis import given
from hypothesis import strategies as st

# ============================================================================
# Python mirror: extractSpanAttributes (flow-table.js)
# ============================================================================


def extract_span_attributes(attrs):
    """Python mirror of extractSpanAttributes from flow-table.js.

    Takes a raw attributes dict (flat key-value map from a span).
    Returns:
      - dict with type='http' and mapped fields when http.request.method is present
      - dict with type='db' and mapped fields when db.system is present (no http)
      - None when neither key is present, or attrs is None/empty

    HTTP detection takes priority over DB when both keys are present.
    Fields with empty/None values are omitted.
    Integer fields (status_code, server_port) use int() with fallback to 0,
    omitted when 0.
    """
    if not attrs:
        return None

    if attrs.get("http.request.method"):
        result = {"type": "http"}
        method = attrs.get("http.request.method")
        if method:
            result["method"] = method
        route = attrs.get("http.route")
        if route:
            result["route"] = route
        path = attrs.get("url.path")
        if path:
            result["path"] = path
        try:
            sc = int(attrs.get("http.response.status_code", 0) or 0)
        except (ValueError, TypeError):
            sc = 0
        if sc:
            result["status_code"] = sc
        sa = attrs.get("server.address")
        if sa:
            result["server_address"] = sa
        try:
            sp = int(attrs.get("server.port", 0) or 0)
        except (ValueError, TypeError):
            sp = 0
        if sp:
            result["server_port"] = sp
        ca = attrs.get("client.address")
        if ca:
            result["client_address"] = ca
        scheme = attrs.get("url.scheme")
        if scheme:
            result["url_scheme"] = scheme
        ua = attrs.get("user_agent.original")
        if ua:
            result["user_agent"] = ua
        return result

    if attrs.get("db.system"):
        result = {"type": "db"}
        sys_val = attrs.get("db.system")
        if sys_val:
            result["system"] = sys_val
        op = attrs.get("db.operation")
        if op:
            result["operation"] = op
        name = attrs.get("db.name")
        if name:
            result["name"] = name
        tbl = attrs.get("db.sql.table")
        if tbl:
            result["table"] = tbl
        stmt = attrs.get("db.statement")
        if stmt:
            result["statement"] = stmt
        cs = attrs.get("db.connection_string")
        if cs:
            result["connection_string"] = cs
        usr = attrs.get("db.user")
        if usr:
            result["user"] = usr
        sa = attrs.get("server.address")
        if sa:
            result["server_address"] = sa
        try:
            sp = int(attrs.get("server.port", 0) or 0)
        except (ValueError, TypeError):
            sp = 0
        if sp:
            result["server_port"] = sp
        return result

    return None


# ============================================================================
# Python mirror: generateContextLine (flow-table.js)
# ============================================================================


def generate_context_line(summary):
    """Python mirror of generateContextLine from flow-table.js.

    Takes an attribute summary (from extract_span_attributes) and returns a string.

    HTTP format: {method} {route_or_path} → {status_code} @ {server_address}:{server_port}
      - Uses route if available, falls back to path.
      - Omits URL component if neither route nor path is present.
      - Omits → {status_code} if no status code.
      - Omits @ {server} suffix if no server_address.

    DB format: {system} {operation} {table} @ {server_address}:{server_port}
      - Omits any component that is absent.
      - Omits @ {server} suffix if no server_address.

    Returns '' if summary is None.
    """
    if not summary:
        return ""

    if summary.get("type") == "http":
        parts = []
        if summary.get("method"):
            parts.append(summary["method"])
        url = summary.get("route") or summary.get("path") or ""
        if url:
            parts.append(url)
        if summary.get("status_code"):
            parts.append("\u2192 " + str(summary["status_code"]))
        line = " ".join(parts)
        if summary.get("server_address"):
            line += " @ " + summary["server_address"]
            if summary.get("server_port"):
                line += ":" + str(summary["server_port"])
        return line

    if summary.get("type") == "db":
        parts = []
        if summary.get("system"):
            parts.append(summary["system"])
        if summary.get("operation"):
            parts.append(summary["operation"])
        if summary.get("table"):
            parts.append(summary["table"])
        line = " ".join(parts)
        if summary.get("server_address"):
            line += " @ " + summary["server_address"]
            if summary.get("server_port"):
                line += ":" + str(summary["server_port"])
        return line

    return ""


# ============================================================================
# Python mirror: status code → CSS class classification
# ============================================================================


def classify_status_code(code):
    """Python mirror of the status code → CSS class logic from flow-table.js.

    Maps an integer HTTP status code to a CSS class suffix:
      200-299 → '2xx'
      300-399 → '3xx'
      400-499 → '4xx'
      500-599 → '5xx'

    Returns None for codes outside these ranges.
    """
    if 200 <= code <= 299:
        return "2xx"
    if 300 <= code <= 399:
        return "3xx"
    if 400 <= code <= 499:
        return "4xx"
    if 500 <= code <= 599:
        return "5xx"
    return None


# ============================================================================
# Python mirror: context line truncation (80-char limit)
# ============================================================================


def truncate_context_line(line):
    """Python mirror of the 80-char truncation logic from flow-table.js _createRow.

    If len(line) > 80: return line[:77] + '...'
    Otherwise return line unchanged.
    """
    if len(line) > 80:
        return line[:77] + "..."
    return line


# ============================================================================
# Hypothesis strategies
# ============================================================================

# Reusable alphabets for generating realistic attribute values
_IDENTIFIER_ALPHABET = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"),
    whitelist_characters="-_.",
)

_PATH_ALPHABET = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"),
    whitelist_characters="-_./{}",
)

_HTTP_METHODS = st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])

_DB_SYSTEMS = st.sampled_from(
    ["postgresql", "mysql", "sqlite", "redis", "mongodb", "mssql", "oracle"]
)

_DB_OPERATIONS = st.sampled_from(
    ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"]
)


def _non_empty_text(min_size=1, max_size=30, alphabet=_IDENTIFIER_ALPHABET):
    """Helper: generates non-empty text strings."""
    return st.text(min_size=min_size, max_size=max_size, alphabet=alphabet)


def _optional_text(min_size=1, max_size=30, alphabet=_IDENTIFIER_ALPHABET):
    """Helper: generates either None or a non-empty text string."""
    return st.one_of(st.none(), _non_empty_text(min_size, max_size, alphabet))


@st.composite
def http_attributes_strategy(draw):
    """Strategy that generates attribute dicts with http.request.method always present.

    Optional HTTP keys: http.route, url.path, http.response.status_code,
    server.address, server.port, client.address, url.scheme, user_agent.original.
    """
    attrs = {}
    # Required: http.request.method
    attrs["http.request.method"] = draw(_HTTP_METHODS)

    # Optional fields
    route = draw(_optional_text(max_size=60, alphabet=_PATH_ALPHABET))
    if route is not None:
        attrs["http.route"] = route

    path = draw(_optional_text(max_size=60, alphabet=_PATH_ALPHABET))
    if path is not None:
        attrs["url.path"] = path

    status_code = draw(st.one_of(st.none(), st.integers(min_value=100, max_value=599)))
    if status_code is not None:
        attrs["http.response.status_code"] = str(status_code)

    server_address = draw(_optional_text(max_size=40))
    if server_address is not None:
        attrs["server.address"] = server_address

    server_port = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=65535)))
    if server_port is not None:
        attrs["server.port"] = str(server_port)

    client_address = draw(_optional_text(max_size=40))
    if client_address is not None:
        attrs["client.address"] = client_address

    scheme = draw(st.one_of(st.none(), st.sampled_from(["http", "https"])))
    if scheme is not None:
        attrs["url.scheme"] = scheme

    user_agent = draw(_optional_text(max_size=80))
    if user_agent is not None:
        attrs["user_agent.original"] = user_agent

    return attrs


@st.composite
def db_attributes_strategy(draw):
    """Strategy that generates attribute dicts with db.system always present.

    Optional DB keys: db.operation, db.name, db.sql.table, db.statement,
    db.connection_string, db.user, server.address, server.port.
    """
    attrs = {}
    # Required: db.system
    attrs["db.system"] = draw(_DB_SYSTEMS)

    # Optional fields
    operation = draw(st.one_of(st.none(), _DB_OPERATIONS))
    if operation is not None:
        attrs["db.operation"] = operation

    name = draw(_optional_text(max_size=30))
    if name is not None:
        attrs["db.name"] = name

    table = draw(_optional_text(max_size=30))
    if table is not None:
        attrs["db.sql.table"] = table

    statement = draw(_optional_text(max_size=100))
    if statement is not None:
        attrs["db.statement"] = statement

    conn_string = draw(_optional_text(max_size=60))
    if conn_string is not None:
        attrs["db.connection_string"] = conn_string

    user = draw(_optional_text(max_size=20))
    if user is not None:
        attrs["db.user"] = user

    server_address = draw(_optional_text(max_size=40))
    if server_address is not None:
        attrs["server.address"] = server_address

    server_port = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=65535)))
    if server_port is not None:
        attrs["server.port"] = str(server_port)

    return attrs


@st.composite
def generic_attributes_strategy(draw):
    """Strategy that generates attribute dicts WITHOUT http.request.method or db.system.

    Generates arbitrary key-value pairs that don't trigger HTTP or DB extraction.
    """
    num_attrs = draw(st.integers(min_value=0, max_value=8))
    keys = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=_IDENTIFIER_ALPHABET,
            ).filter(lambda k: k not in ("http.request.method", "db.system")),
            min_size=num_attrs,
            max_size=num_attrs,
            unique=True,
        )
    )
    values = draw(
        st.lists(
            st.text(max_size=50),
            min_size=num_attrs,
            max_size=num_attrs,
        )
    )
    return dict(zip(keys, values, strict=True))


def any_span_attributes_strategy():
    """Strategy that generates one of: HTTP attrs, DB attrs, or generic attrs."""
    return st.one_of(
        http_attributes_strategy(),
        db_attributes_strategy(),
        generic_attributes_strategy(),
    )


@st.composite
def http_summary_strategy(draw):
    """Strategy that generates HTTP summary dicts directly.

    type='http' with method always present, optional fields:
    route, path, status_code, server_address, server_port,
    client_address, url_scheme, user_agent.
    """
    summary = {"type": "http"}
    summary["method"] = draw(_HTTP_METHODS)

    route = draw(_optional_text(max_size=60, alphabet=_PATH_ALPHABET))
    if route is not None:
        summary["route"] = route

    path = draw(_optional_text(max_size=60, alphabet=_PATH_ALPHABET))
    if path is not None:
        summary["path"] = path

    status_code = draw(st.one_of(st.none(), st.integers(min_value=100, max_value=599)))
    if status_code is not None:
        summary["status_code"] = status_code

    server_address = draw(_optional_text(max_size=40))
    if server_address is not None:
        summary["server_address"] = server_address

    server_port = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=65535)))
    if server_port is not None:
        summary["server_port"] = server_port

    client_address = draw(_optional_text(max_size=40))
    if client_address is not None:
        summary["client_address"] = client_address

    scheme = draw(st.one_of(st.none(), st.sampled_from(["http", "https"])))
    if scheme is not None:
        summary["url_scheme"] = scheme

    user_agent = draw(_optional_text(max_size=80))
    if user_agent is not None:
        summary["user_agent"] = user_agent

    return summary


@st.composite
def db_summary_strategy(draw):
    """Strategy that generates DB summary dicts directly.

    type='db' with system always present, optional fields:
    operation, name, table, statement, connection_string, user,
    server_address, server_port.
    """
    summary = {"type": "db"}
    summary["system"] = draw(_DB_SYSTEMS)

    operation = draw(st.one_of(st.none(), _DB_OPERATIONS))
    if operation is not None:
        summary["operation"] = operation

    name = draw(_optional_text(max_size=30))
    if name is not None:
        summary["name"] = name

    table = draw(_optional_text(max_size=30))
    if table is not None:
        summary["table"] = table

    statement = draw(_optional_text(max_size=100))
    if statement is not None:
        summary["statement"] = statement

    conn_string = draw(_optional_text(max_size=60))
    if conn_string is not None:
        summary["connection_string"] = conn_string

    user = draw(_optional_text(max_size=20))
    if user is not None:
        summary["user"] = user

    server_address = draw(_optional_text(max_size=40))
    if server_address is not None:
        summary["server_address"] = server_address

    server_port = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=65535)))
    if server_port is not None:
        summary["server_port"] = server_port

    return summary


# ============================================================================
# Smoke tests — verify mirrors and strategies are functional
# ============================================================================


@given(attrs=any_span_attributes_strategy())
def test_extract_span_attributes_smoke(attrs):
    """Smoke test: extract_span_attributes runs without error on generated attrs."""
    result = extract_span_attributes(attrs)
    assert result is None or isinstance(result, dict)


@given(summary=st.one_of(http_summary_strategy(), db_summary_strategy()))
def test_generate_context_line_smoke(summary):
    """Smoke test: generate_context_line runs without error on generated summaries."""
    result = generate_context_line(summary)
    assert isinstance(result, str)


@given(code=st.integers(min_value=100, max_value=599))
def test_classify_status_code_smoke(code):
    """Smoke test: classify_status_code runs without error on generated codes."""
    result = classify_status_code(code)
    assert result is None or result in ("2xx", "3xx", "4xx", "5xx")


@given(line=st.text(min_size=0, max_size=200))
def test_truncate_context_line_smoke(line):
    """Smoke test: truncate_context_line runs without error on generated strings."""
    result = truncate_context_line(line)
    assert isinstance(result, str)
    assert len(result) <= 80


# ============================================================================
# Unit tests — specific examples and edge cases
# Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.2, 2.5, 2.6, 3.4, 5.1, 5.2
# ============================================================================


def test_extract_http_full():
    """All HTTP fields present — verify complete summary."""
    attrs = {
        "http.request.method": "PUT",
        "http.route": "/v1/runners/{runnerName}/heartbeat",
        "url.path": "/v1/runners/r1/heartbeat",
        "http.response.status_code": "204",
        "server.address": "essvt",
        "server.port": "8080",
        "client.address": "10.0.0.1",
        "url.scheme": "http",
        "user_agent.original": "python-requests/2.31",
    }
    result = extract_span_attributes(attrs)
    assert result is not None
    assert result["type"] == "http"
    assert result["method"] == "PUT"
    assert result["route"] == "/v1/runners/{runnerName}/heartbeat"
    assert result["path"] == "/v1/runners/r1/heartbeat"
    assert result["status_code"] == 204
    assert result["server_address"] == "essvt"
    assert result["server_port"] == 8080
    assert result["client_address"] == "10.0.0.1"
    assert result["url_scheme"] == "http"
    assert result["user_agent"] == "python-requests/2.31"


def test_extract_db_full():
    """All DB fields present — verify complete summary."""
    attrs = {
        "db.system": "postgresql",
        "db.operation": "SELECT",
        "db.name": "testdb",
        "db.sql.table": "runner_t",
        "db.statement": "SELECT * FROM runner_t WHERE id = $1",
        "db.connection_string": "postgresql://localhost:5432/testdb",
        "db.user": "appuser",
        "server.address": "postgres",
        "server.port": "5432",
    }
    result = extract_span_attributes(attrs)
    assert result is not None
    assert result["type"] == "db"
    assert result["system"] == "postgresql"
    assert result["operation"] == "SELECT"
    assert result["name"] == "testdb"
    assert result["table"] == "runner_t"
    assert result["statement"] == "SELECT * FROM runner_t WHERE id = $1"
    assert result["connection_string"] == "postgresql://localhost:5432/testdb"
    assert result["user"] == "appuser"
    assert result["server_address"] == "postgres"
    assert result["server_port"] == 5432


def test_extract_null_attrs():
    """Null input returns None."""
    assert extract_span_attributes(None) is None


def test_extract_empty_attrs():
    """Empty dict returns None."""
    assert extract_span_attributes({}) is None


def test_extract_empty_values_omitted():
    """Keys present with empty string values are omitted from result."""
    attrs = {
        "http.request.method": "GET",
        "http.route": "",
        "url.path": "",
        "http.response.status_code": "",
        "server.address": "",
        "server.port": "",
        "client.address": "",
        "url.scheme": "",
        "user_agent.original": "",
    }
    result = extract_span_attributes(attrs)
    assert result is not None
    assert result == {"type": "http", "method": "GET"}


def test_extract_http_priority_over_db():
    """Attrs with both http.request.method and db.system returns HTTP."""
    attrs = {
        "http.request.method": "POST",
        "db.system": "postgresql",
        "db.operation": "INSERT",
    }
    result = extract_span_attributes(attrs)
    assert result is not None
    assert result["type"] == "http"
    assert result["method"] == "POST"
    assert "system" not in result


def test_context_line_http_with_route():
    """Verify route used over path when both present."""
    summary = {
        "type": "http",
        "method": "PUT",
        "route": "/v1/runners",
        "path": "/v1/runners/r1",
        "status_code": 204,
        "server_address": "essvt",
        "server_port": 8080,
    }
    result = generate_context_line(summary)
    assert result == "PUT /v1/runners \u2192 204 @ essvt:8080"


def test_context_line_http_with_path_fallback():
    """Verify path used when no route."""
    summary = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "status_code": 200,
    }
    result = generate_context_line(summary)
    assert result == "GET /api/health \u2192 200"


def test_context_line_http_no_url():
    """Verify method + status only when no route/path."""
    summary = {
        "type": "http",
        "method": "POST",
        "status_code": 201,
    }
    result = generate_context_line(summary)
    assert result == "POST \u2192 201"


def test_context_line_db_minimal():
    """System only — minimal DB context line."""
    summary = {
        "type": "db",
        "system": "postgresql",
    }
    result = generate_context_line(summary)
    assert result == "postgresql"


def test_context_line_null_returns_empty():
    """Null summary returns empty string."""
    assert generate_context_line(None) == ""


def test_context_line_server_suffix():
    """Verify @ server:port appended for DB context line."""
    summary = {
        "type": "db",
        "system": "postgresql",
        "operation": "SELECT",
        "table": "runner_t",
        "server_address": "postgres",
        "server_port": 5432,
    }
    result = generate_context_line(summary)
    assert result == "postgresql SELECT runner_t @ postgres:5432"


def test_status_code_boundary_values():
    """Boundary values for status code classification."""
    assert classify_status_code(199) is None
    assert classify_status_code(200) == "2xx"
    assert classify_status_code(299) == "2xx"
    assert classify_status_code(300) == "3xx"
    assert classify_status_code(399) == "3xx"
    assert classify_status_code(400) == "4xx"
    assert classify_status_code(499) == "4xx"
    assert classify_status_code(500) == "5xx"
    assert classify_status_code(599) == "5xx"


def test_truncation_exactly_80():
    """80-char string unchanged."""
    line = "A" * 80
    assert truncate_context_line(line) == line
    assert len(truncate_context_line(line)) == 80


def test_truncation_81_chars():
    """81-char string truncated to 77 + '...'."""
    line = "B" * 81
    result = truncate_context_line(line)
    assert result == "B" * 77 + "..."
    assert len(result) == 80


# ============================================================================
# Property tests
# ============================================================================

# --- Design Property 1: Attribute extraction correctness ---
# For any attributes object, extract_span_attributes shall return:
# - HTTP summary when http.request.method is present
# - DB summary when db.system is present (and no http.request.method)
# - None when neither key is present
# Fields with empty/None/zero values are omitted.
# Validates: Requirements 1.1, 1.2, 1.3, 1.5

# HTTP field mapping: source attr key → result field name
_HTTP_FIELD_MAP = {
    "http.request.method": "method",
    "http.route": "route",
    "url.path": "path",
    "server.address": "server_address",
    "client.address": "client_address",
    "url.scheme": "url_scheme",
    "user_agent.original": "user_agent",
}

_HTTP_INT_FIELD_MAP = {
    "http.response.status_code": "status_code",
    "server.port": "server_port",
}

# DB field mapping: source attr key → result field name
_DB_FIELD_MAP = {
    "db.system": "system",
    "db.operation": "operation",
    "db.name": "name",
    "db.sql.table": "table",
    "db.statement": "statement",
    "db.connection_string": "connection_string",
    "db.user": "user",
    "server.address": "server_address",
}

_DB_INT_FIELD_MAP = {
    "server.port": "server_port",
}


@given(attrs=any_span_attributes_strategy())
def test_property_extraction_correctness(attrs):
    """Property 1: Attribute extraction correctness.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.5**
    """
    result = extract_span_attributes(attrs)

    has_http = bool(attrs.get("http.request.method"))
    has_db = bool(attrs.get("db.system"))

    # Requirement 1.3: neither key → None
    if not has_http and not has_db:
        assert result is None
        return

    assert isinstance(result, dict)

    if has_http:
        # Requirement 1.1: HTTP detection takes priority
        assert result["type"] == "http"

        # Verify string fields
        for src_key, result_key in _HTTP_FIELD_MAP.items():
            src_val = attrs.get(src_key)
            if src_val:
                assert result_key in result
                assert result[result_key] == src_val
            else:
                assert result_key not in result

        # Verify integer fields
        for src_key, result_key in _HTTP_INT_FIELD_MAP.items():
            raw = attrs.get(src_key, 0) or 0
            try:
                parsed = int(raw)
            except (ValueError, TypeError):
                parsed = 0
            if parsed:
                assert result_key in result
                assert result[result_key] == parsed
            else:
                assert result_key not in result

    else:
        # Requirement 1.2: DB summary
        assert result["type"] == "db"

        # Verify string fields
        for src_key, result_key in _DB_FIELD_MAP.items():
            src_val = attrs.get(src_key)
            if src_val:
                assert result_key in result
                assert result[result_key] == src_val
            else:
                assert result_key not in result

        # Verify integer fields
        for src_key, result_key in _DB_INT_FIELD_MAP.items():
            raw = attrs.get(src_key, 0) or 0
            try:
                parsed = int(raw)
            except (ValueError, TypeError):
                parsed = 0
            if parsed:
                assert result_key in result
                assert result[result_key] == parsed
            else:
                assert result_key not in result

    # Requirement 1.5: no extra keys beyond 'type' and mapped fields
    if result["type"] == "http":
        allowed = {"type"} | set(_HTTP_FIELD_MAP.values()) | set(_HTTP_INT_FIELD_MAP.values())
    else:
        allowed = {"type"} | set(_DB_FIELD_MAP.values()) | set(_DB_INT_FIELD_MAP.values())
    assert set(result.keys()) <= allowed


# --- Design Property 2: HTTP context line format ---
# For any HTTP attribute summary, generate_context_line shall produce a string
# where: method appears first; route appears next (or path if route is absent);
# → {status_code} appears if status_code is present; and
# @ {server_address}:{server_port} is appended if server_address is present.
# Route is always preferred over path when both are present.
# Validates: Requirements 2.1, 2.5, 5.1


@given(summary=http_summary_strategy())
def test_property_http_context_line_format(summary):
    """Property 2: HTTP context line format.

    **Validates: Requirements 2.1, 2.5, 5.1**
    """
    result = generate_context_line(summary)

    # 1. The result is a string
    assert isinstance(result, str)

    # 2. If method is present, it appears at the start of the line
    if summary.get("method"):
        assert result.startswith(summary["method"])

    # 3. If route is present, route appears in the line (preferred over path)
    if summary.get("route"):
        assert summary["route"] in result

    # 4. If route is absent but path is present, path appears in the line
    if not summary.get("route") and summary.get("path"):
        assert summary["path"] in result

    # 5. If status_code is present, → {status_code} appears in the line
    if summary.get("status_code"):
        assert "\u2192 " + str(summary["status_code"]) in result

    # 6. If server_address is present, @ {server_address} appears in the line
    if summary.get("server_address"):
        assert "@ " + summary["server_address"] in result

    # 7. If server_address and server_port are both present,
    #    @ {server_address}:{server_port} appears
    if summary.get("server_address") and summary.get("server_port"):
        expected_server = "@ " + summary["server_address"] + ":" + str(summary["server_port"])
        assert expected_server in result


# --- Design Property 3: DB context line format ---
# For any DB attribute summary, generateContextLine shall produce a string
# containing the present components (system, operation, table) in order
# separated by spaces, with @ {server_address} appended if server_address
# is present (port included only when non-zero). Components that are absent
# shall not appear in the output.
# Validates: Requirements 2.2, 5.2


@given(summary=db_summary_strategy())
def test_property_db_context_line_format(summary):
    """Property 3: DB context line format.

    **Validates: Requirements 2.2, 5.2**
    """
    result = generate_context_line(summary)

    # 1. The result is a string
    assert isinstance(result, str)

    # 2. If system is present, it appears in the line
    if summary.get("system"):
        assert summary["system"] in result

    # 3. If operation is present, it appears in the line
    if summary.get("operation"):
        assert summary["operation"] in result

    # 4. If table is present, it appears in the line
    if summary.get("table"):
        assert summary["table"] in result

    # 5. Components appear in order: system before operation, operation before table
    if summary.get("system") and summary.get("operation"):
        assert result.index(summary["system"]) < result.index(summary["operation"])
    if summary.get("operation") and summary.get("table"):
        assert result.index(summary["operation"]) < result.index(summary["table"])

    # 6. If server_address is present, @ {server_address} appears in the line
    if summary.get("server_address"):
        assert "@ " + summary["server_address"] in result

    # 7. If server_address and server_port are both present,
    #    @ {server_address}:{server_port} appears
    if summary.get("server_address") and summary.get("server_port"):
        expected_server = "@ " + summary["server_address"] + ":" + str(summary["server_port"])
        assert expected_server in result
