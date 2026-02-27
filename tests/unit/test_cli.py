"""Unit tests for CLI entry point."""

import io
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rf_trace_viewer.cli import main
from rf_trace_viewer.generator import ReportOptions


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
                            mock_options.assert_called_once_with(
                                title="Custom Report Title",
                                compact=False,
                                gzip_embed=False,
                                max_keyword_depth=None,
                                exclude_passing_keywords=False,
                                max_spans=None,
                            )

    def test_live_mode_argument(self, monkeypatch):
        """CLI with --live should create and start a LiveServer."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "--live",
            ],
        )

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            mock_server_cls.assert_called_once_with(
                trace_path="tests/fixtures/simple_trace.json",
                port=8077,
                title=None,
                poll_interval=5,
                receiver_mode=False,
                journal_path="traces.journal.json",
                forward_url=None,
                output_path="trace-report.html",
                report_options=ReportOptions(
                    title=None,
                    compact=False,
                    gzip_embed=False,
                    max_keyword_depth=None,
                    exclude_passing_keywords=False,
                    max_spans=None,
                ),
                provider=None,
                base_url=None,
                lookback=None,
                max_spans=500000,
            )
            mock_server.start.assert_called_once_with(open_browser=True)

    def test_port_argument(self, monkeypatch):
        """CLI with --port should pass port number to LiveServer."""
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

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            mock_server_cls.assert_called_once_with(
                trace_path="tests/fixtures/simple_trace.json",
                port=9000,
                title=None,
                poll_interval=5,
                receiver_mode=False,
                journal_path="traces.journal.json",
                forward_url=None,
                output_path="trace-report.html",
                report_options=ReportOptions(
                    title=None,
                    compact=False,
                    gzip_embed=False,
                    max_keyword_depth=None,
                    exclude_passing_keywords=False,
                    max_spans=None,
                ),
                provider=None,
                base_url=None,
                lookback=None,
                max_spans=500000,
            )

    def test_no_open_argument(self, monkeypatch):
        """CLI with --no-open should pass open_browser=False to LiveServer.start()."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "--live",
                "--no-open",
            ],
        )

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            mock_server.start.assert_called_once_with(open_browser=False)

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

        with patch(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)],
        ):
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

        with patch(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/pabot_trace.json", "-o", str(output_file)],
        ):
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

        with patch(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/all_types_trace.json", "-o", str(output_file)],
        ):
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

        with patch(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/malformed_trace.json", "-o", str(output_file)],
        ):
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

        with patch(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)],
        ):
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

        with patch(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)],
        ):
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

        with patch(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)],
        ):
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


class TestServeSubcommand:
    """Test the 'serve' subcommand behavior."""

    def test_serve_starts_live_server(self, monkeypatch):
        """'serve' subcommand should start LiveServer without requiring input file."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve"])

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            mock_server_cls.assert_called_once_with(
                trace_path="",
                port=8077,
                title=None,
                poll_interval=5,
                receiver_mode=False,
                journal_path="traces.journal.json",
                forward_url=None,
                output_path="trace-report.html",
                report_options=ReportOptions(
                    title=None,
                    compact=False,
                    gzip_embed=False,
                    max_keyword_depth=None,
                    exclude_passing_keywords=False,
                    max_spans=None,
                ),
                provider=None,
                base_url=None,
                lookback=None,
                max_spans=500000,
            )
            mock_server.start.assert_called_once_with(open_browser=True)

    def test_serve_with_custom_port(self, monkeypatch):
        """'serve --port 9000' should pass port to LiveServer."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve", "--port", "9000"])

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            assert mock_server_cls.call_args.kwargs["port"] == 9000

    def test_serve_provider_signoz_without_endpoint_exits_1(self, monkeypatch, capsys):
        """'serve --provider signoz' without endpoint should exit with code 1."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve", "--provider", "signoz"])
        monkeypatch.delenv("SIGNOZ_ENDPOINT", raising=False)

        exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "--provider signoz requires --signoz-endpoint" in captured.err

    def test_serve_provider_signoz_with_endpoint_ok(self, monkeypatch):
        """'serve --provider signoz --signoz-endpoint <url>' should succeed."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "serve",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
            ],
        )

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0

    def test_serve_provider_signoz_with_env_var_ok(self, monkeypatch):
        """'serve --provider signoz' with SIGNOZ_ENDPOINT env var should succeed."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve", "--provider", "signoz"])
        monkeypatch.setenv("SIGNOZ_ENDPOINT", "https://signoz.example.com")

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0

    def test_serve_provider_json_ignores_signoz_config(self, monkeypatch):
        """'serve --provider json' should work without any SigNoz config."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve", "--provider", "json"])
        monkeypatch.delenv("SIGNOZ_ENDPOINT", raising=False)

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0

    def test_serve_default_provider_is_json(self, monkeypatch):
        """'serve' without --provider should default to json and not require SigNoz config."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve"])
        monkeypatch.delenv("SIGNOZ_ENDPOINT", raising=False)

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0

    def test_serve_with_no_open(self, monkeypatch):
        """'serve --no-open' should pass open_browser=False."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve", "--no-open"])

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            mock_server.start.assert_called_once_with(open_browser=False)

    def test_legacy_command_still_works_with_serve_subcommand(self, monkeypatch, tmp_path):
        """Legacy 'rf-trace-report <file>' should still work when serve subcommand exists."""
        output_file = tmp_path / "report.html"

        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "-o",
                str(output_file),
            ],
        )

        exit_code = main()

        assert exit_code == 0
        assert output_file.exists()


class TestSigNozArguments:
    """Test CLI argument parsing for SigNoz provider options."""

    # --- Argument parsing for new options on the default command ---

    def test_provider_argument_defaults_to_json(self, monkeypatch, tmp_path):
        """Default --provider should be 'json' when not specified."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)],
        )

        with (
            patch("rf_trace_viewer.cli.parse_file") as mock_parse,
            patch("rf_trace_viewer.cli.build_tree") as mock_tree,
            patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret,
            patch("rf_trace_viewer.cli.generate_report") as mock_generate,
        ):
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
            # json provider uses direct pipeline (parse_file called)
            mock_parse.assert_called_once()

    def test_provider_signoz_static_mode(self, monkeypatch, tmp_path):
        """--provider signoz in static mode should use provider pipeline."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli._run_provider_pipeline") as mock_pipeline:
            mock_pipeline.return_value = 0

            exit_code = main()

            assert exit_code == 0
            mock_pipeline.assert_called_once()
            config = mock_pipeline.call_args[0][0]
            assert config.provider == "signoz"
            assert config.signoz_endpoint == "https://signoz.example.com"

    def test_provider_signoz_without_endpoint_exits_error(self, monkeypatch, capsys):
        """--provider signoz without --signoz-endpoint should exit with code 1."""
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "--provider", "signoz"],
        )
        monkeypatch.delenv("SIGNOZ_ENDPOINT", raising=False)

        exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "--provider signoz requires --signoz-endpoint" in captured.err

    def test_signoz_endpoint_argument(self, monkeypatch, tmp_path):
        """--signoz-endpoint should be passed through to config."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://my-signoz.io",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli._run_provider_pipeline") as mock_pipeline:
            mock_pipeline.return_value = 0
            main()
            config = mock_pipeline.call_args[0][0]
            assert config.signoz_endpoint == "https://my-signoz.io"

    def test_signoz_api_key_argument(self, monkeypatch, tmp_path):
        """--signoz-api-key should be passed through to config."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "--signoz-api-key",
                "my-secret-key",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli._run_provider_pipeline") as mock_pipeline:
            mock_pipeline.return_value = 0
            main()
            config = mock_pipeline.call_args[0][0]
            assert config.signoz_api_key == "my-secret-key"

    def test_execution_attribute_argument(self, monkeypatch, tmp_path):
        """--execution-attribute should override the default."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "--execution-attribute",
                "custom.exec_id",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli._run_provider_pipeline") as mock_pipeline:
            mock_pipeline.return_value = 0
            main()
            config = mock_pipeline.call_args[0][0]
            assert config.execution_attribute == "custom.exec_id"

    def test_max_spans_per_page_argument(self, monkeypatch, tmp_path):
        """--max-spans-per-page should be passed through to config."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "--max-spans-per-page",
                "5000",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli._run_provider_pipeline") as mock_pipeline:
            mock_pipeline.return_value = 0
            main()
            config = mock_pipeline.call_args[0][0]
            assert config.max_spans_per_page == 5000

    def test_overlap_window_argument(self, monkeypatch, tmp_path):
        """--overlap-window should be passed through to config."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "--overlap-window",
                "5.0",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli._run_provider_pipeline") as mock_pipeline:
            mock_pipeline.return_value = 0
            main()
            config = mock_pipeline.call_args[0][0]
            assert config.overlap_window_seconds == 5.0

    def test_config_file_argument(self, monkeypatch, tmp_path):
        """--config should be accepted and the config file should be loaded."""
        config_file = tmp_path / "my_config.json"
        config_file.write_text('{"title": "Config Title"}')
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "--config",
                str(config_file),
                "-o",
                str(output_file),
            ],
        )

        with (
            patch("rf_trace_viewer.cli.parse_file") as mock_parse,
            patch("rf_trace_viewer.cli.build_tree") as mock_tree,
            patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret,
            patch("rf_trace_viewer.cli.generate_report") as mock_generate,
        ):
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

    # --- provider json ignores SigNoz config ---

    def test_provider_json_ignores_signoz_arguments(self, monkeypatch, tmp_path):
        """--provider json should work even when SigNoz args are provided."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "tests/fixtures/simple_trace.json",
                "--provider",
                "json",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "--signoz-api-key",
                "some-key",
                "-o",
                str(output_file),
            ],
        )

        with (
            patch("rf_trace_viewer.cli.parse_file") as mock_parse,
            patch("rf_trace_viewer.cli.build_tree") as mock_tree,
            patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret,
            patch("rf_trace_viewer.cli.generate_report") as mock_generate,
        ):
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
            # json provider uses parse_file, not the provider pipeline
            mock_parse.assert_called_once_with("tests/fixtures/simple_trace.json")

    # --- Existing behavior unchanged ---

    def test_no_provider_flag_uses_json_pipeline(self, monkeypatch, tmp_path):
        """Without --provider, the legacy json pipeline should be used."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json", "-o", str(output_file)],
        )

        with (
            patch("rf_trace_viewer.cli.parse_file") as mock_parse,
            patch("rf_trace_viewer.cli.build_tree") as mock_tree,
            patch("rf_trace_viewer.cli.interpret_tree") as mock_interpret,
            patch("rf_trace_viewer.cli.generate_report") as mock_generate,
        ):
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

    def test_no_input_file_without_provider_exits_error(self, monkeypatch, capsys):
        """Without input file and without --provider signoz, should exit with error."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report"])

        exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "input file is required" in captured.err

    def test_signoz_provider_no_input_file_ok(self, monkeypatch, tmp_path):
        """--provider signoz should not require an input file."""
        output_file = tmp_path / "report.html"
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "-o",
                str(output_file),
            ],
        )

        with patch("rf_trace_viewer.cli._run_provider_pipeline") as mock_pipeline:
            mock_pipeline.return_value = 0

            exit_code = main()

            assert exit_code == 0

    # --- serve subcommand with SigNoz arguments ---

    def test_serve_signoz_all_arguments(self, monkeypatch):
        """serve with all SigNoz arguments should pass them through."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "serve",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
                "--signoz-api-key",
                "key123",
                "--execution-attribute",
                "my.exec_id",
                "--max-spans-per-page",
                "2000",
                "--overlap-window",
                "3.5",
                "--poll-interval",
                "10",
            ],
        )

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            mock_server.start.assert_called_once()

    def test_serve_is_recognized_as_subcommand(self, monkeypatch):
        """'serve' should be recognized and not treated as an input file."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve"])

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            # Should start live server, not try to parse 'serve' as a file
            mock_server.start.assert_called_once()

    def test_invalid_provider_choice_exits_error(self, monkeypatch, capsys):
        """--provider with invalid value should exit with error."""
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "tests/fixtures/simple_trace.json", "--provider", "invalid"],
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 2  # argparse exits with 2 for invalid choices


class TestServeSubcommandEndToEnd:
    """Test serve subcommand wires provider and base_url end-to-end (Task 51.2)."""

    def test_serve_signoz_builds_provider(self, monkeypatch):
        """serve --provider signoz should build SigNozProvider and pass to LiveServer."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "serve",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "https://signoz.example.com",
            ],
        )

        with (
            patch("rf_trace_viewer.server.LiveServer") as mock_server_cls,
            patch("rf_trace_viewer.cli._build_provider") as mock_build,
        ):
            mock_provider = MagicMock()
            mock_build.return_value = mock_provider
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            mock_build.assert_called_once()
            # Provider should be passed to LiveServer
            assert mock_server_cls.call_args.kwargs["provider"] is mock_provider

    def test_serve_json_provider_is_none(self, monkeypatch):
        """serve --provider json should pass provider=None to LiveServer."""
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "serve", "--provider", "json"],
        )

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            assert mock_server_cls.call_args.kwargs["provider"] is None

    def test_serve_default_provider_passes_none(self, monkeypatch):
        """serve without --provider should pass provider=None (json default)."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve"])

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            assert mock_server_cls.call_args.kwargs["provider"] is None

    def test_serve_env_var_config_docker_use_case(self, monkeypatch):
        """serve --provider signoz with env vars only (Docker deployment)."""
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "serve", "--provider", "signoz"],
        )
        monkeypatch.setenv("SIGNOZ_ENDPOINT", "https://signoz.internal:3301")
        monkeypatch.setenv("SIGNOZ_API_KEY", "docker-secret-key")

        with (
            patch("rf_trace_viewer.server.LiveServer") as mock_server_cls,
            patch("rf_trace_viewer.cli._build_provider") as mock_build,
        ):
            mock_provider = MagicMock()
            mock_build.return_value = mock_provider
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            # Verify _build_provider was called (env vars resolved by load_config)
            mock_build.assert_called_once()
            config = mock_build.call_args[0][0]
            assert config.signoz_endpoint == "https://signoz.internal:3301"
            assert config.signoz_api_key == "docker-secret-key"

    def test_serve_base_url_passed_to_server(self, monkeypatch):
        """serve --base-url should propagate to LiveServer."""
        monkeypatch.setattr(
            "sys.argv",
            ["rf-trace-report", "serve", "--base-url", "/trace-viewer"],
        )

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            assert mock_server_cls.call_args.kwargs["base_url"] == "/trace-viewer"

    def test_serve_base_url_default_none(self, monkeypatch):
        """serve without --base-url should pass base_url=None."""
        monkeypatch.setattr("sys.argv", ["rf-trace-report", "serve"])

        with patch("rf_trace_viewer.server.LiveServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            assert mock_server_cls.call_args.kwargs["base_url"] is None

    def test_serve_sidecar_localhost_endpoint(self, monkeypatch):
        """Sidecar deployment: SIGNOZ_ENDPOINT=http://localhost:3301."""
        monkeypatch.setattr(
            "sys.argv",
            [
                "rf-trace-report",
                "serve",
                "--provider",
                "signoz",
                "--signoz-endpoint",
                "http://localhost:3301",
            ],
        )

        with (
            patch("rf_trace_viewer.server.LiveServer") as mock_server_cls,
            patch("rf_trace_viewer.cli._build_provider") as mock_build,
        ):
            mock_provider = MagicMock()
            mock_build.return_value = mock_provider
            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            exit_code = main()

            assert exit_code == 0
            config = mock_build.call_args[0][0]
            assert config.signoz_endpoint == "http://localhost:3301"
            mock_build.assert_called_once()
