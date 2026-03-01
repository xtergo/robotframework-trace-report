"""Unit tests for static mode header rendering.

Verifies that when window.__RF_TRACE_LIVE__ is falsy, the header renders
only: Logo Slot (if configured), title, flex spacer, and Dark Mode Icon.
No Status Cluster, Pause/Resume, or Diagnostics Panel appear in static mode.

Validates: Requirements 12.1, 12.4
"""

import re
from pathlib import Path


def _load_app_js():
    """Return the raw content of app.js."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "rf_trace_viewer"
        / "viewer"
        / "app.js"
    )
    return path.read_text(encoding="utf-8")


def _extract_init_app_body(js):
    """Extract the body of the _initApp function from app.js."""
    start = js.find("function _initApp(data)")
    assert start != -1, "_initApp function not found in app.js"
    # Walk forward to find the matching closing brace
    brace_count = 0
    body_start = js.find("{", start)
    for i in range(body_start, len(js)):
        if js[i] == "{":
            brace_count += 1
        elif js[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                return js[body_start : i + 1]
    raise AssertionError("Could not find end of _initApp function")


def _find_live_guard_blocks(fn_body):
    """Return list of (start, end) index ranges for `if (window.__RF_TRACE_LIVE__)` blocks."""
    blocks = []
    pattern = re.compile(r"if\s*\(\s*window\.__RF_TRACE_LIVE__\s*\)")
    for m in pattern.finditer(fn_body):
        # Find the opening brace of this if-block
        brace_start = fn_body.find("{", m.end())
        if brace_start == -1:
            continue
        depth = 0
        for i in range(brace_start, len(fn_body)):
            if fn_body[i] == "{":
                depth += 1
            elif fn_body[i] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append((brace_start, i + 1))
                    break
    return blocks


def _is_inside_live_guard(fn_body, position, live_blocks):
    """Check if a position falls inside any __RF_TRACE_LIVE__ guard block."""
    for start, end in live_blocks:
        if start <= position < end:
            return True
    return False


class TestLiveOnlyElementsGuarded:
    """Live-mode elements must only be created inside __RF_TRACE_LIVE__ guards."""

    def test_status_cluster_inside_live_guard(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)
        blocks = _find_live_guard_blocks(fn)
        assert len(blocks) >= 1, "Expected at least one __RF_TRACE_LIVE__ guard"

        match = re.search(r"['\"]status-cluster['\"]", fn)
        assert match is not None, "status-cluster class not found in _initApp"
        assert _is_inside_live_guard(
            fn, match.start(), blocks
        ), "status-cluster must be created inside __RF_TRACE_LIVE__ guard"

    def test_pause_resume_btn_inside_live_guard(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)
        blocks = _find_live_guard_blocks(fn)

        match = re.search(r"['\"]pause-resume-btn['\"]", fn)
        assert match is not None, "pause-resume-btn class not found in _initApp"
        assert _is_inside_live_guard(
            fn, match.start(), blocks
        ), "pause-resume-btn must be created inside __RF_TRACE_LIVE__ guard"

    def test_diagnostics_panel_inside_live_guard(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)
        blocks = _find_live_guard_blocks(fn)

        match = re.search(r"['\"]diagnostics-panel['\"]", fn)
        assert match is not None, "diagnostics-panel class not found in _initApp"
        assert _is_inside_live_guard(
            fn, match.start(), blocks
        ), "diagnostics-panel must be created inside __RF_TRACE_LIVE__ guard"


class TestAlwaysRenderedElements:
    """Elements that render in both static and live modes must be outside live guards."""

    def test_header_spacer_outside_live_guard(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)
        blocks = _find_live_guard_blocks(fn)

        match = re.search(r"['\"]header-spacer['\"]", fn)
        assert match is not None, "header-spacer class not found in _initApp"
        assert not _is_inside_live_guard(
            fn, match.start(), blocks
        ), "header-spacer must be rendered outside __RF_TRACE_LIVE__ guard"

    def test_theme_toggle_icon_outside_live_guard(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)
        blocks = _find_live_guard_blocks(fn)

        match = re.search(r"['\"]theme-toggle-icon['\"]", fn)
        assert match is not None, "theme-toggle-icon class not found in _initApp"
        assert not _is_inside_live_guard(
            fn, match.start(), blocks
        ), "theme-toggle-icon must be rendered outside __RF_TRACE_LIVE__ guard"

    def test_title_h1_outside_live_guard(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)
        blocks = _find_live_guard_blocks(fn)

        # The title is created via createElement('h1')
        match = re.search(r"createElement\(['\"]h1['\"]\)", fn)
        assert match is not None, "h1 element creation not found in _initApp"
        assert not _is_inside_live_guard(
            fn, match.start(), blocks
        ), "Title h1 must be rendered outside __RF_TRACE_LIVE__ guard"


class TestAppReadyAfterHeader:
    """The app-ready event must emit after the header is appended to the DOM."""

    def test_app_ready_emitted_after_header_append(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)

        header_append = fn.find("root.appendChild(header)")
        assert header_append != -1, "root.appendChild(header) not found"

        app_ready = fn.find("emit('app-ready'")
        assert app_ready != -1, "app-ready event emission not found"

        assert app_ready > header_append, "app-ready must be emitted after root.appendChild(header)"


class TestLogoSlotGuard:
    """Logo Slot must be guarded by __RF_LOGO_URL__, not __RF_TRACE_LIVE__."""

    def test_logo_guarded_by_logo_url(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)

        # Find the logo URL guard
        logo_guard = re.search(r"if\s*\(\s*window\.__RF_LOGO_URL__\s*\)", fn)
        assert logo_guard is not None, "Logo slot must be guarded by window.__RF_LOGO_URL__"

    def test_logo_not_guarded_by_trace_live(self):
        js = _load_app_js()
        fn = _extract_init_app_body(js)
        blocks = _find_live_guard_blocks(fn)

        logo_guard = re.search(r"if\s*\(\s*window\.__RF_LOGO_URL__\s*\)", fn)
        assert logo_guard is not None
        assert not _is_inside_live_guard(
            fn, logo_guard.start(), blocks
        ), "Logo slot guard must NOT be inside __RF_TRACE_LIVE__ block"
