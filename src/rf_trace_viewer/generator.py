"""HTML report generator — produces self-contained HTML from span tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from rf_trace_viewer.rf_model import (
    RFRunModel,
)

# Order matters: stats.js, tree.js, timeline.js, keyword-stats.js, and search.js define functions used by app.js
_JS_FILES = (
    "stats.js",
    "tree.js",
    "timeline.js",
    "keyword-stats.js",
    "search.js",
    "theme.js",
    "app.js",
)
_CSS_FILES = ("style.css",)
_VIEWER_DIR = Path(__file__).parent / "viewer"


@dataclass
class ReportOptions:
    """Options controlling report generation."""

    title: str | None = None
    theme: str = "system"  # "light", "dark", "system"
    compact: bool = False  # omit default-value fields from embedded JSON


def _serialize(obj: Any) -> Any:
    """Recursively serialize dataclasses, enums, and primitives to JSON-safe types."""
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize(getattr(obj, k)) for k in obj.__dataclass_fields__}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


_COMPACT_DEFAULTS = ("", [], {}, 0)


def _serialize_compact(obj: Any) -> Any:
    """Recursively serialize like _serialize but omit dataclass fields at default empty values.

    Fields are omitted when their serialized value is ``""``, ``[]``, ``{}``, or ``0`` (int).
    ``0.0`` (float), ``False``, and ``None`` are NOT omitted — timestamps and durations use floats.
    Only dataclass fields are subject to omission; plain dict keys are always kept.
    """
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for k in obj.__dataclass_fields__:
            v = _serialize_compact(getattr(obj, k))
            # Skip fields whose serialized value is one of the default empties.
            # Use explicit type checks so 0.0 and False are not skipped.
            if v == "" or v == [] or v == {} or (v == 0 and type(v) is int):
                continue
            result[k] = v
        return result
    if isinstance(obj, list):
        return [_serialize_compact(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize_compact(v) for k, v in obj.items()}
    return obj


def embed_data(model: RFRunModel, compact: bool = False) -> str:
    """Serialize RFRunModel to a JSON string for embedding in HTML."""
    serializer = _serialize_compact if compact else _serialize
    return json.dumps(serializer(model), separators=(",", ":"))


def embed_viewer_assets() -> tuple[str, str]:
    """Read and return (js_content, css_content) from the viewer/ directory.

    Raises FileNotFoundError if any expected asset file is missing.
    """
    js_parts: list[str] = []
    for name in _JS_FILES:
        path = _VIEWER_DIR / name
        if not path.exists():
            raise FileNotFoundError(
                f"Viewer asset missing: {path}  — installation may be corrupted"
            )
        js_parts.append(path.read_text(encoding="utf-8"))

    css_parts: list[str] = []
    for name in _CSS_FILES:
        path = _VIEWER_DIR / name
        if not path.exists():
            raise FileNotFoundError(
                f"Viewer asset missing: {path}  — installation may be corrupted"
            )
        css_parts.append(path.read_text(encoding="utf-8"))

    return "\n".join(js_parts), "\n".join(css_parts)


def generate_report(model: RFRunModel, options: ReportOptions | None = None) -> str:
    """Generate a self-contained HTML5 report string.

    The output contains all data, JS, and CSS inline — no external dependencies.
    """
    if options is None:
        options = ReportOptions()

    # Strip whitespace and use default if empty
    title = (options.title or "").strip() or (model.title or "").strip() or "RF Trace Report"
    data_json = embed_data(model, compact=options.compact)
    js_content, css_content = embed_viewer_assets()

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_escape_html(title)}</title>\n"
        "<style>\n"
        f"{css_content}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="rf-trace-viewer"></div>\n'
        "<script>\n"
        f"window.__RF_TRACE_DATA__ = {data_json};\n"
        "</script>\n"
        "<script>\n"
        f"{js_content}\n"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    )


def _escape_html(text: str) -> str:
    """Minimal HTML escaping for text content."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
