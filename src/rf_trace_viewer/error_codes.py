"""Error codes and structured error response builders.

Provides a canonical set of error codes for the trace-report API and
helper functions that produce consistently shaped error / warning
JSON bodies.  All functions are pure (no I/O, no side-effects) and
use only the Python standard library.
"""

ERROR_CODES = frozenset(
    {
        "AUTH_MISSING",
        "AUTH_EXPIRED",
        "CLICKHOUSE_TIMEOUT",
        "CLICKHOUSE_UNREACHABLE",
        "SIGNOZ_TIMEOUT",
        "SIGNOZ_UNREACHABLE",
        "DNS_FAIL",
        "TLS_ERROR",
        "RATE_LIMITED",
        "MAX_SPANS_TRUNCATED",
        "INTERNAL_ERROR",
    }
)


def error_response(
    error_code: str,
    message: str,
    request_id: str,
    status: int = 500,
    warning: str | None = None,
) -> tuple[int, dict]:
    """Build a standard error response.

    Parameters
    ----------
    error_code:
        One of the values in :data:`ERROR_CODES`.
    message:
        Human-readable description of the error.
    request_id:
        The ``X-Request-Id`` for this request.
    status:
        HTTP status code (default 500).
    warning:
        Optional warning string appended to the body.

    Returns
    -------
    tuple[int, dict]
        ``(status_code, json_body)`` ready to be serialised and sent.

    Raises
    ------
    ValueError
        If *error_code* is not in :data:`ERROR_CODES`.
    """
    if error_code not in ERROR_CODES:
        raise ValueError(
            f"Unknown error code {error_code!r}. " f"Must be one of {sorted(ERROR_CODES)}"
        )

    body: dict = {
        "error_code": error_code,
        "message": message,
        "request_id": request_id,
    }
    if warning is not None:
        body["warning"] = warning

    return status, body


def truncation_warning(data: dict, error_code: str, limit: int) -> dict:
    """Add a ``warning`` field to a successful response payload.

    Used when the result set has been truncated to *limit* items
    (typically ``MAX_SPANS_TRUNCATED``).

    Parameters
    ----------
    data:
        The original response payload dict.  A *shallow copy* is
        returned — the original is not mutated.
    error_code:
        The warning code (e.g. ``"MAX_SPANS_TRUNCATED"``).
    limit:
        The cap that was applied.

    Returns
    -------
    dict
        A copy of *data* with an added ``warning`` field.

    Raises
    ------
    ValueError
        If *error_code* is not in :data:`ERROR_CODES`.
    """
    if error_code not in ERROR_CODES:
        raise ValueError(
            f"Unknown error code {error_code!r}. " f"Must be one of {sorted(ERROR_CODES)}"
        )

    result = dict(data)
    result["warning"] = {"code": error_code, "limit": limit}
    return result
