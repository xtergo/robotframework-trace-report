"""Session management for the MCP Trace Analyzer."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rf_trace_viewer.parser import RawLogRecord, RawSpan, parse_file
from rf_trace_viewer.rf_model import RFRunModel, interpret_tree
from rf_trace_viewer.tree import SpanNode, build_tree


class ToolError(Exception):
    """Base for tool-level errors."""


class AliasNotFoundError(ToolError):
    """Raised when a run alias is not in the session."""


class TestNotFoundError(ToolError):
    """Raised when a test name doesn't match any test in the run."""

    def __init__(self, test_name: str, available: list[str]):
        self.test_name = test_name
        self.available = available
        super().__init__(f"Test {test_name!r} not found. Available tests: {available}")


@dataclass
class RunData:
    """In-memory representation of a single loaded test execution."""

    alias: str
    spans: list[RawSpan]
    logs: list[RawLogRecord]
    roots: list[SpanNode]
    model: RFRunModel
    log_index: dict[str, list[RawLogRecord]]


@dataclass
class Session:
    """Holds zero or more loaded runs keyed by user-assigned aliases."""

    runs: dict[str, RunData] = field(default_factory=dict)

    def load_run(
        self,
        alias: str,
        trace_path: str,
        log_path: str | None = None,
    ) -> RunData:
        """Parse trace/log files and store the result under *alias*.

        Replaces any existing data for the same alias.
        """
        spans: list[RawSpan] = parse_file(trace_path)
        roots = build_tree(spans)
        model = interpret_tree(roots)

        logs: list[RawLogRecord] = []
        if log_path is not None:
            result = parse_file(log_path, include_logs=True)
            logs = result.logs

        log_index: dict[str, list[RawLogRecord]] = defaultdict(list)
        for record in logs:
            log_index[record.span_id].append(record)

        run_data = RunData(
            alias=alias,
            spans=spans,
            logs=logs,
            roots=roots,
            model=model,
            log_index=dict(log_index),
        )
        self.runs[alias] = run_data
        return run_data

    def get_run(self, alias: str) -> RunData:
        """Return the :class:`RunData` for *alias*.

        Raises :class:`KeyError` with a descriptive message when the
        alias is not loaded.
        """
        try:
            return self.runs[alias]
        except KeyError:
            raise KeyError(
                f"Run alias {alias!r} not loaded. " f"Loaded aliases: {sorted(self.runs)}"
            ) from None
