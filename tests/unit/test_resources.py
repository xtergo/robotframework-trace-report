"""Unit tests for rf_trace_viewer.resources module."""

from __future__ import annotations

from unittest.mock import mock_open, patch

from rf_trace_viewer.resources import (
    _get_cpu_limit_millicores,
    _get_memory_limit_kb,
    _parse_proc_status,
    get_resource_snapshot,
)


class TestParseProcStatus:
    def test_returns_rss_and_vsize(self):
        content = "VmSize:\t  102400 kB\nVmRSS:\t   51200 kB\nOther: foo\n"
        with patch("rf_trace_viewer.resources._read_file", return_value=content):
            result = _parse_proc_status()
        assert result == {"rss_kb": 51200, "vsize_kb": 102400}

    def test_returns_empty_when_file_missing(self):
        with patch("rf_trace_viewer.resources._read_file", return_value=None):
            assert _parse_proc_status() == {}


class TestGetMemoryLimitKb:
    def test_cgroup_v2(self):
        with patch(
            "rf_trace_viewer.resources._read_file",
            side_effect=lambda p: "536870912\n" if "memory.max" in p else None,
        ):
            assert _get_memory_limit_kb() == 536870912 // 1024

    def test_cgroup_v2_max_means_no_limit(self):
        with patch(
            "rf_trace_viewer.resources._read_file",
            side_effect=lambda p: "max\n" if "memory.max" in p else None,
        ):
            assert _get_memory_limit_kb() is None

    def test_cgroup_v1(self):
        def _fake_read(path):
            if "memory.max" in path:
                return None
            if "memory.limit_in_bytes" in path:
                return "268435456\n"
            return None

        with patch("rf_trace_viewer.resources._read_file", side_effect=_fake_read):
            assert _get_memory_limit_kb() == 268435456 // 1024


class TestGetCpuLimitMillicores:
    def test_cgroup_v2(self):
        with patch(
            "rf_trace_viewer.resources._read_file",
            side_effect=lambda p: "50000 100000\n" if "cpu.max" in p else None,
        ):
            assert _get_cpu_limit_millicores() == 500

    def test_cgroup_v2_max_means_no_limit(self):
        with patch(
            "rf_trace_viewer.resources._read_file",
            side_effect=lambda p: "max 100000\n" if "cpu.max" in p else None,
        ):
            assert _get_cpu_limit_millicores() is None

    def test_cgroup_v1(self):
        def _fake_read(path):
            if "cpu.max" in path:
                return None
            if "cfs_quota_us" in path:
                return "25000\n"
            if "cfs_period_us" in path:
                return "100000\n"
            return None

        with patch("rf_trace_viewer.resources._read_file", side_effect=_fake_read):
            assert _get_cpu_limit_millicores() == 250


class TestGetResourceSnapshot:
    def test_returns_all_keys(self):
        snapshot = get_resource_snapshot()
        assert "rss_mb" in snapshot
        assert "rss_limit_mb" in snapshot
        assert "rss_pct" in snapshot
        assert "cpu_pct" in snapshot
        assert "cpu_limit_mc" in snapshot

    def test_rss_mb_is_numeric(self):
        snapshot = get_resource_snapshot()
        assert isinstance(snapshot["rss_mb"], (int, float))

    def test_with_mocked_proc(self):
        def _fake_read(path):
            if path == "/proc/self/status":
                return "VmRSS:\t  102400 kB\nVmSize:\t  204800 kB\n"
            if path == "/sys/fs/cgroup/memory.max":
                return "524288000\n"  # 500 MB
            if path == "/sys/fs/cgroup/cpu.max":
                return "50000 100000\n"  # 500m
            if path == "/proc/self/stat":
                return None  # skip CPU for simplicity
            return None

        with patch("rf_trace_viewer.resources._read_file", side_effect=_fake_read):
            snapshot = get_resource_snapshot()

        assert snapshot["rss_mb"] == 100.0
        assert snapshot["rss_limit_mb"] == 500.0
        assert snapshot["rss_pct"] == 20.0
        assert snapshot["cpu_limit_mc"] == 500
