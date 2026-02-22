"""Unit tests for CLI entry point."""

import io
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rf_trace_viewer.cli import main


class TestArgumentParsing:
    """Test CLI argument parsing for all options."""

    def test_minimal_arguments(self, monkeypatch, tmp_path):
        """CLI with only input file should use defaults."""
        output_file = tmp_path / "trace-report.html"
        
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json"],
        )
        
        # Change to tmp_path so default output goes there
        monkeypatch.chdir(tmp_path)

        with patch("rf_trace_viewer.cli.parse_file") as mock_parse:
            with patch("rf_trace_viewer.cli.build_tree") as mock_tree:
                with patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret:
                    with patch("rf_trace_viewer.cli.generate_report") as mock_generate:
                        # Setup mocks
                        mock_parse.return_value = []
                        mock_tree.return_value = []
                        mock_model = MagicMock()
                        mock_model.statistics.total_tests = 0
                        mock_model.statistics.passed = 0
                        mock_model.statistics.failed = 0
                        mock_model.statistics.skipped = 0
                        mock_interpret.return_value = mock_model
                        mock_generate.return_value = "<html></html>"

                        exit_code = main()

                        assert exit_code == 0
                        mock_parse.assert_called_once_with("tests/fixtures/simple_trace.json")
                        assert output_file.exists()

    def test_output_argument(self, monkeypatch, tmp_path):
        """CLI with -o/--output should use specified output path."""
        output_file = tmp_path / "custom-report.html"

        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli.parse_file") as mock_parse:
            with patch("rf_trace_viewer.cli.build_tree") as mock_tree:
                with patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret:
                    with patch("rf_trace_viewer.cli.generate_report") as mock_generate:
                        # Setup mocks
                        mock_parse.return_value = []
                        mock_tree.return_value = []
                        mock_model = MagicMock()
                        mock_model.statistics.total_tests = 0
                        mock_model.statistics.passed = 0
                        mock_model.statistics.failed = 0
                        mock_model.statistics.skipped = 0
                        mock_interpret.return_value = mock_model
                        mock_generate.return_value = "<html></html>"

                        exit_code = main()

                        assert exit_code == 0
                        assert output_file.exists()
                        assert output_file.read_text() == "<html></html>"

    def test_title_argument(self, monkeypatch, tmp_path):
        """CLI with --title should pass title to ReportOptions."""
        output_file = tmp_path / "report.html"

        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "-o",
                str(output_file),
                "--title",
                "Custom Report Title",
            ],
        )

        with patch("rf_trace_viewer.cli.parse_file") as mock_parse:
            with patch("rf_trace_viewer.cli.build_tree") as mock_tree:
                with patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret:
                    with patch("rf_trace_viewer.cli.generate_report") as mock_generate:
                        with patch("rf_trace_viewer.cli.ReportOptions") as mock_options:
                            # Setup mocks
                            mock_parse.return_value = []
                            mock_tree.return_value = []
                            mock_model = MagicMock()
                            mock_model.statistics.total_tests = 0
                            mock_model.statistics.passed = 0
                            mock_model.statistics.failed = 0
                            mock_model.statistics.skipped = 0
                            mock_interpret.return_value = mock_model
                            mock_generate.return_value = "<html></html>"

                            exit_code = main()

                            assert exit_code == 0
                            mock_options.assert_called_once_with(title="Custom Report Title")

    def test_live_mode_argument(self, monkeypatch, capsys):
        """CLI with --live should indicate live mode (not yet implemented)."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "--live",
            ],
        )

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Live mode not yet implemented" in captured.out

    def test_port_argument(self, monkeypatch, capsys):
        """CLI with --port should accept port number for live mode."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "--live",
                "--port",
                "9000",
            ],
        )

        exit_code = main()

        assert exit_code == 0
        # Port argument should be parsed without error
        captured = capsys.readouterr()
        assert "Live mode not yet implemented" in captured.out

    def test_no_open_argument(self, monkeypatch, capsys):
        """CLI with --no-open should accept flag for live mode."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "--live",
                "--no-open",
            ],
        )

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Live mode not yet implemented" in captured.out

    def test_version_argument(self, monkeypatch, capsys):
        """CLI with --version should print version and exit."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "--version"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "rf-trace-report" in captured.out


class TestErrorCases:
    """Test CLI error handling."""

    def test_missing_input_file(self, monkeypatch, capsys):
        """CLI with nonexistent input file should exit with error."""
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "nonexistent_file.json"],
        )

        exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "nonexistent_file.json" in captured.err

    def test_unwritable_output_path(self, monkeypatch, capsys):
        """CLI with unwritable output path should exit with error."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "-o",
                "/root/unwritable/report.html",
            ],
        )

        with patch("rf_trace_viewer.cli.parse_file") as mock_parse:
            with patch("rf_trace_viewer.cli.build_tree") as mock_tree:
                with patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret:
                    with patch("rf_trace_viewer.cli.generate_report") as mock_generate:
                        # Setup mocks
                        mock_parse.return_value = []
                        mock_tree.return_value = []
                        mock_model = MagicMock()
                        mock_model.statistics.total_tests = 0
                        mock_model.statistics.passed = 0
                        mock_model.statistics.failed = 0
                        mock_model.statistics.skipped = 0
                        mock_interpret.return_value = mock_model
                        mock_generate.return_value = "<html></html>"

                        exit_code = main()

                        assert exit_code == 1
                        captured = capsys.readouterr()
                        assert "Error:" in captured.err
                        assert "Permission denied" in captured.err or "No such file" in captured.err

    def test_invalid_json_in_input_file(self, monkeypatch, capsys, tmp_path):
        """CLI with invalid JSON should handle parse errors gracefully."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json at all")

        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", str(invalid_file)],
        )

        # The parser should handle this gracefully and return empty list
        # CLI should succeed with 0 spans
        with patch("rf_trace_viewer.cli.build_tree") as mock_tree:
            with patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret:
                with patch("rf_trace_viewer.cli.generate_report") as mock_generate:
                    mock_tree.return_value = []
                    mock_model = MagicMock()
                    mock_model.statistics.total_tests = 0
                    mock_model.statistics.passed = 0
                    mock_model.statistics.failed = 0
                    mock_model.statistics.skipped = 0
                    mock_interpret.return_value = mock_model
                    mock_generate.return_value = "<html></html>"

                    output_file = tmp_path / "report.html"
                    monkeypatch.setattr(
                        "sys.argv",
                        ["rf-trace-report", str(invalid_file), "-o", str(output_file)],
                    )

                    exit_code = main()

                    # Should succeed with 0 spans (parser handles malformed lines)
                    assert exit_code == 0
                    captured = capsys.readouterr()
                    assert "0 spans" in captured.out


class TestStaticModeEndToEnd:
    """Test static mode end-to-end with fixture data."""

    def test_simple_trace_end_to_end(self, tmp_path):
        """Generate report from simple_trace.json fixture."""
        output_file = tmp_path / "simple-report.html"

        with patch("sys.argv", ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)]):
            exit_code = main()

        assert exit_code == 0
        assert output_file.exists()

        # Verify HTML content
        html_content = output_file.read_text()
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content
        assert "</html>" in html_content
        assert "Simple Suite" in html_content  # Suite name from fixture

    def test_pabot_trace_end_to_end(self, tmp_path):
        """Generate report from pabot_trace.json fixture."""
        output_file = tmp_path / "pabot-report.html"

        with patch("sys.argv", ["rf-trace-report", "tests/fixtures/pabot_trace.json", "-o", str(output_file)]):
            exit_code = main()

        assert exit_code == 0
        assert output_file.exists()

        # Verify HTML content
        html_content = output_file.read_text()
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content
        assert "</html>" in html_content

    def test_all_types_trace_end_to_end(self, tmp_path):
        """Generate report from all_types_trace.json fixture."""
        output_file = tmp_path / "all-types-report.html"

        with patch("sys.argv", ["rf-trace-report", "tests/fixtures/all_types_trace.json", "-o", str(output_file)]):
            exit_code = main()

        assert exit_code == 0
        assert output_file.exists()

        # Verify HTML content
        html_content = output_file.read_text()
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content
        assert "</html>" in html_content

    def test_malformed_trace_end_to_end(self, tmp_path, capsys):
        """Generate report from malformed_trace.json fixture (should skip bad lines)."""
        output_file = tmp_path / "malformed-report.html"

        with patch("sys.argv", ["rf-trace-report", "tests/fixtures/malformed_trace.json", "-o", str(output_file)]):
            # Should succeed despite malformed lines
            exit_code = main()

        assert exit_code == 0
        assert output_file.exists()

        # Verify HTML content
        html_content = output_file.read_text()
        assert "<!DOCTYPE html>" in html_content

    def test_stdin_input_end_to_end(self, tmp_path, monkeypatch):
        """Generate report from stdin input."""
        output_file = tmp_path / "stdin-report.html"

        # Read fixture content
        fixture_content = Path("tests/fixtures/simple_trace.json").read_text()

        # Mock stdin
        monkeypatch.setattr("sys.stdin", io.StringIO(fixture_content))

        with patch("sys.argv", ["rf-trace-report", "-", "-o", str(output_file)]):
            exit_code = main()

        assert exit_code == 0
        assert output_file.exists()

        # Verify HTML content
        html_content = output_file.read_text()
        assert "<!DOCTYPE html>" in html_content
        assert "Simple Suite" in html_content

    def test_custom_title_end_to_end(self, tmp_path):
        """Generate report with custom title."""
        output_file = tmp_path / "custom-title-report.html"

        with patch(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "-o",
                str(output_file),
                "--title",
                "My Custom Test Report",
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        assert output_file.exists()

        # Verify custom title in HTML
        html_content = output_file.read_text()
        assert "My Custom Test Report" in html_content

    def test_output_summary_message(self, tmp_path, capsys):
        """CLI should print summary message with test counts."""
        output_file = tmp_path / "report.html"

        with patch("sys.argv", ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)]):
            exit_code = main()

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Report generated:" in captured.out
        assert str(output_file) in captured.out
        assert "spans" in captured.out
        assert "tests" in captured.out
        assert "passed" in captured.out


class TestCLIPipeline:
    """Test the complete CLI pipeline: parse → build tree → interpret → generate → write."""

    def test_pipeline_calls_all_components(self, tmp_path):
        """CLI should call all pipeline components in correct order."""
        output_file = tmp_path / "pipeline-report.html"

        with patch("sys.argv", ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)]):
            with patch("rf_trace_viewer.cli.parse_file") as mock_parse:
                with patch("rf_trace_viewer.cli.build_tree") as mock_tree:
                    with patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret:
                        with patch("rf_trace_viewer.cli.generate_report") as mock_generate:
                            # Setup mocks
                            mock_spans = [MagicMock()]
                            mock_roots = [MagicMock()]
                            mock_model = MagicMock()
                            mock_model.statistics.total_tests = 1
                            mock_model.statistics.passed = 1
                            mock_model.statistics.failed = 0
                            mock_model.statistics.skipped = 0

                            mock_parse.return_value = mock_spans
                            mock_tree.return_value = mock_roots
                            mock_interpret.return_value = mock_model
                            mock_generate.return_value = "<html>Test Report</html>"

                            exit_code = main()

                            assert exit_code == 0

                            # Verify call order
                            mock_parse.assert_called_once_with("tests/fixtures/simple_trace.json")
                            mock_tree.assert_called_once_with(mock_spans)
                            mock_interpret.assert_called_once_with(mock_roots)
                            mock_generate.assert_called_once()

                            # Verify output file written
                            assert output_file.exists()
                            assert output_file.read_text() == "<html>Test Report</html>"

    def test_pipeline_propagates_data_correctly(self, tmp_path):
        """CLI should propagate data correctly through pipeline."""
        output_file = tmp_path / "data-report.html"

        with patch("sys.argv", ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)]):
            with patch("rf_trace_viewer.cli.parse_file") as mock_parse:
                with patch("rf_trace_viewer.cli.build_tree") as mock_tree:
                    with patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret:
                        with patch("rf_trace_viewer.cli.generate_report") as mock_generate:
                            # Create mock data with identifiable attributes
                            mock_span = MagicMock()
                            mock_span.name = "Test Span"
                            mock_spans = [mock_span]

                            mock_root = MagicMock()
                            mock_root.span = mock_span
                            mock_roots = [mock_root]

                            mock_model = MagicMock()
                            mock_model.statistics.total_tests = 1
                            mock_model.statistics.passed = 1
                            mock_model.statistics.failed = 0
                            mock_model.statistics.skipped = 0

                            mock_parse.return_value = mock_spans
                            mock_tree.return_value = mock_roots
                            mock_interpret.return_value = mock_model
                            mock_generate.return_value = "<html></html>"

                            exit_code = main()

                            assert exit_code == 0

                            # Verify data passed correctly
                            assert mock_tree.call_args[0][0] == mock_spans
                            assert mock_interpret.call_args[0][0] == mock_roots
                            assert mock_generate.call_args[0][0] == mock_model
