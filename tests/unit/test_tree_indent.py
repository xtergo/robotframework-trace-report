"""Unit tests for configurable tree indentation feature.

Validates Requirements 36.1, 36.2, 36.3, 36.5, 36.7:
- Default --tree-indent-size is 24px in generated HTML
- Slider control has min=8, max=48, step=4 attributes
- Changing slider updates CSS custom property on document.documentElement
- Truncated indicator padding uses configured indent size (not hardcoded 16)
- localStorage round-trip for indent persistence
- Depth-0 nodes always have margin-left: 0
"""

import re
from pathlib import Path

from rf_trace_viewer.generator import embed_viewer_assets, generate_report
from rf_trace_viewer.parser import parse_file
from rf_trace_viewer.rf_model import interpret_tree
from rf_trace_viewer.tree import build_tree


def _load_html():
    """Generate a full HTML report from simple_trace.json fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "simple_trace.json"
    spans = parse_file(str(fixture_path))
    trees = build_tree(spans)
    model = interpret_tree(trees)
    return generate_report(model)


def _load_assets():
    """Return (js_content, css_content) from the viewer directory."""
    return embed_viewer_assets()


class TestCSSDefaultIndentation:
    """Validates: Requirement 36.1 — default indentation is 24px."""

    def test_css_has_tree_indent_size_24px(self):
        """The CSS custom property --tree-indent-size defaults to 24px."""
        _, css = _load_assets()
        assert "--tree-indent-size: 24px" in css

    def test_generated_html_contains_indent_custom_property(self):
        """The generated HTML embeds CSS with --tree-indent-size: 24px."""
        html = _load_html()
        assert "--tree-indent-size: 24px" in html

    def test_tree_node_uses_css_variable_for_margin(self):
        """Tree nodes use var(--tree-indent-size) for margin-left, not a hardcoded value."""
        _, css = _load_assets()
        # Should find margin-left: var(--tree-indent-size) in the .tree-node rule
        assert "margin-left: var(--tree-indent-size)" in css

    def test_depth_0_nodes_have_zero_margin(self):
        """Depth-0 nodes always have margin-left: 0 regardless of indent setting."""
        _, css = _load_assets()
        # Find the depth-0 rule
        assert ".tree-node.depth-0" in css
        # Extract the depth-0 rule block and verify margin-left: 0
        idx = css.find(".tree-node.depth-0")
        block_start = css.find("{", idx)
        block_end = css.find("}", block_start)
        depth0_block = css[block_start:block_end]
        assert "margin-left: 0" in depth0_block

    def test_dark_theme_also_has_24px_default(self):
        """Dark theme also sets --tree-indent-size: 24px."""
        _, css = _load_assets()
        # Find the dark theme block and verify it also has the property
        dark_idx = css.find(".theme-dark")
        assert dark_idx != -1
        dark_section = css[dark_idx : dark_idx + 1000]
        assert "--tree-indent-size: 24px" in dark_section


class TestSliderControlAttributes:
    """Validates: Requirement 36.2 — slider with min=8, max=48, step=4."""

    def test_slider_min_attribute(self):
        """The indent slider has min='8'."""
        js, _ = _load_assets()
        assert "slider.min = '8'" in js

    def test_slider_max_attribute(self):
        """The indent slider has max='48'."""
        js, _ = _load_assets()
        assert "slider.max = '48'" in js

    def test_slider_step_attribute(self):
        """The indent slider has step='4'."""
        js, _ = _load_assets()
        assert "slider.step = '4'" in js

    def test_slider_type_is_range(self):
        """The indent slider is an input[type=range]."""
        js, _ = _load_assets()
        assert "slider.type = 'range'" in js

    def test_slider_has_aria_label(self):
        """The indent slider has an aria-label for accessibility."""
        js, _ = _load_assets()
        assert "aria-label" in js
        assert "Tree indentation size" in js

    def test_slider_embedded_in_html(self):
        """The generated HTML contains the slider JS code."""
        html = _load_html()
        assert "slider.min = '8'" in html
        assert "slider.max = '48'" in html
        assert "slider.step = '4'" in html


class TestSliderUpdatesCSSProperty:
    """Validates: Requirement 36.3 — slider changes update CSS custom property."""

    def test_slider_sets_css_custom_property_on_input(self):
        """The slider input handler sets --tree-indent-size on the .rf-trace-viewer element."""
        js, _ = _load_assets()
        assert "_getIndentTarget().style.setProperty('--tree-indent-size'" in js

    def test_slider_updates_cached_indent_size(self):
        """The slider input handler updates _cachedIndentSize."""
        js, _ = _load_assets()
        # The handler should assign the parsed value to _cachedIndentSize
        assert "_cachedIndentSize = val" in js

    def test_slider_updates_display_label(self):
        """The slider input handler updates the value display span."""
        js, _ = _load_assets()
        assert "valSpan.textContent = val + 'px'" in js


class TestLocalStoragePersistence:
    """Validates: Requirement 36.5 — localStorage round-trip."""

    def test_reads_from_localstorage_on_init(self):
        """_initIndentSize reads from localStorage key 'rf-trace-indent-size'."""
        js, _ = _load_assets()
        assert "localStorage.getItem('rf-trace-indent-size')" in js

    def test_writes_to_localstorage_on_change(self):
        """Slider change writes to localStorage key 'rf-trace-indent-size'."""
        js, _ = _load_assets()
        assert "localStorage.setItem('rf-trace-indent-size'" in js

    def test_validates_saved_value_range(self):
        """Saved value is validated to be between 8 and 48."""
        js, _ = _load_assets()
        assert "val >= 8" in js
        assert "val <= 48" in js

    def test_localstorage_errors_are_caught(self):
        """localStorage operations are wrapped in try/catch for environments where it's unavailable."""
        js, _ = _load_assets()
        # Both getItem and setItem should be in try blocks
        # Find the _initIndentSize function and verify try/catch
        init_idx = js.find("function _initIndentSize")
        assert init_idx != -1
        init_block = js[init_idx : init_idx + 500]
        assert "try {" in init_block
        assert "catch" in init_block


class TestTruncatedIndicatorUsesConfiguredIndent:
    """Validates: Requirement 36.7 — truncated indicator uses _cachedIndentSize."""

    def test_truncated_indicator_uses_cached_indent_size(self):
        """Truncated indicator paddingLeft uses _cachedIndentSize, not hardcoded 16."""
        js, _ = _load_assets()
        # Should use _cachedIndentSize in the padding calculation
        assert "_cachedIndentSize" in js
        # The truncated indicator line should reference _cachedIndentSize
        pattern = re.compile(r"truncEl\.style\.paddingLeft\s*=.*_cachedIndentSize")
        match = pattern.search(js)
        assert match is not None, "Truncated indicator should use _cachedIndentSize for padding"

    def test_truncated_indicator_not_hardcoded_16(self):
        """Truncated indicator padding does NOT use hardcoded 16px per depth level."""
        js, _ = _load_assets()
        # Find the truncated indicator padding line
        trunc_lines = [line for line in js.splitlines() if "truncEl.style.paddingLeft" in line]
        assert len(trunc_lines) > 0, "Should have truncated indicator padding line"
        for line in trunc_lines:
            # Should NOT contain "depth * 16" — should use _cachedIndentSize instead
            assert (
                "* 16" not in line
            ), f"Truncated indicator should not use hardcoded 16: {line.strip()}"


class TestSliderSynchronization:
    """Test that multiple slider instances stay in sync."""

    def test_slider_sync_array_exists(self):
        """Module-level _indentSliders array tracks all slider instances."""
        js, _ = _load_assets()
        assert "var _indentSliders = []" in js

    def test_slider_pushed_to_sync_array(self):
        """Each created slider is pushed to _indentSliders for sync."""
        js, _ = _load_assets()
        assert "_indentSliders.push(" in js

    def test_slider_syncs_other_sliders_on_input(self):
        """When one slider changes, other sliders are updated to match."""
        js, _ = _load_assets()
        # The input handler should iterate _indentSliders and update others
        assert "entry.slider.value = String(val)" in js
        assert "entry.valSpan.textContent = val + 'px'" in js
