"""HTML report generator — produces self-contained HTML from span tree."""

from __future__ import annotations

import base64
import gzip
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
    gzip_embed: bool = False  # gzip-compress and base64-encode embedded JSON data


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


# Maps original field names → short aliases for compact JSON encoding.
# The reverse mapping (short → original) is embedded in the wrapper as `km`
# so the JS viewer can decode the compact format.
KEY_MAP: dict[str, str] = {
    "name": "n",
    "type": "t",
    "status": "s",
    "start_time": "st",
    "end_time": "et",
    "elapsed_time": "el",
    "children": "ch",
    "events": "ev",
    "attributes": "at",
    "keyword_type": "kt",
    "status_message": "sm",
    "doc": "d",
    "lineno": "ln",
    "args": "a",
    "tags": "tg",
    "metadata": "md",
}


def _apply_key_map(obj: Any, key_map: dict[str, str]) -> Any:
    """Recursively rename dict keys using key_map.

    - Dicts: rename each key if present in key_map, recurse into values.
    - Lists: recurse into each item.
    - Primitives: return as-is.
    """
    if isinstance(obj, dict):
        return {key_map.get(k, k): _apply_key_map(v, key_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_apply_key_map(item, key_map) for item in obj]
    return obj


def _build_intern_table(obj: Any) -> list[str]:
    """Walk a serialized (JSON-safe) object and return an intern table.

    The intern table is a list of string *values* (not keys) that appear more
    than once in the object, sorted by frequency descending (most frequent first).
    Only string values are interned; dict keys are never interned.
    """
    from collections import Counter

    counts: Counter[str] = Counter()

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            counts[node] += 1
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(obj)
    # Keep only strings that appear more than once
    repeated = [(s, c) for s, c in counts.items() if c > 1]
    # Sort by frequency descending, then alphabetically for determinism
    repeated.sort(key=lambda x: (-x[1], x[0]))
    return [s for s, _ in repeated]


def _apply_intern_table(obj: Any, intern_table: list[str]) -> Any:
    """Replace string values that are in intern_table with their integer index.

    Only string *values* are replaced; dict keys are left unchanged.
    Strings not present in intern_table are left as-is.
    """
    index: dict[str, int] = {s: i for i, s in enumerate(intern_table)}

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            return index.get(node, node)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(obj)


def embed_data(model: RFRunModel, compact: bool = False) -> str:
    """Serialize RFRunModel to a JSON string for embedding in HTML.

    When ``compact=True``, the output is wrapped in a versioned envelope::

        {"v":1,"km":{<short→original>},"data":{<span tree with short keys>}}

    The JS viewer checks for ``raw.v`` to detect compact format and uses ``km``
    to decode the short keys back to their original names.

    When ``compact=False``, the raw serialized model is returned unchanged
    (legacy format, no ``v`` field).
    """
    if compact:
        serialized = _serialize_compact(model)
        short_keyed = _apply_key_map(serialized, KEY_MAP)
        intern_table = _build_intern_table(short_keyed)
        interned = _apply_intern_table(short_keyed, intern_table)
        wrapper = {
            "v": 1,
            # km maps short alias → original field name (for JS decoder)
            "km": {v: k for k, v in KEY_MAP.items()},
            "it": intern_table,
            "data": interned,
        }
        return json.dumps(wrapper, separators=(",", ":"))
    return json.dumps(_serialize(model), separators=(",", ":"))


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

    if options.gzip_embed:
        data_bytes = data_json.encode("utf-8")
        compressed = gzip.compress(data_bytes, compresslevel=9)
        b64_string = base64.b64encode(compressed).decode("ascii")
        data_script = f'window.__RF_TRACE_DATA_GZ__ = "{b64_string}";\n'
    else:
        data_script = f"window.__RF_TRACE_DATA__ = {data_json};\n"

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
        f"{data_script}"
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
