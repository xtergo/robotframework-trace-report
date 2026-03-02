"""Lightweight process resource metrics from /proc (Linux only).

Reads RSS memory and CPU usage without external dependencies.
Falls back gracefully on non-Linux platforms.
"""

from __future__ import annotations

import os
import time


def _read_file(path: str) -> str | None:
    """Read a file, returning None if it doesn't exist."""
    try:
        with open(path) as f:
            return f.read()
    except (OSError, PermissionError):
        return None


def _parse_proc_status() -> dict:
    """Parse /proc/self/status for VmRSS and VmSize."""
    content = _read_file("/proc/self/status")
    if not content:
        return {}
    result = {}
    for line in content.splitlines():
        if line.startswith("VmRSS:"):
            result["rss_kb"] = int(line.split()[1])
        elif line.startswith("VmSize:"):
            result["vsize_kb"] = int(line.split()[1])
    return result


def _get_memory_limit_kb() -> int | None:
    """Read container memory limit from cgroup v2 or v1."""
    # cgroup v2
    content = _read_file("/sys/fs/cgroup/memory.max")
    if content and content.strip() != "max":
        try:
            return int(content.strip()) // 1024
        except ValueError:
            pass

    # cgroup v1
    content = _read_file("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if content:
        try:
            val = int(content.strip())
            # Kernel uses a huge number to mean "no limit"
            if val < 2**62:
                return val // 1024
        except ValueError:
            pass

    return None


# CPU tracking state (module-level for delta computation)
_prev_cpu_time: float | None = None
_prev_wall_time: float | None = None


def _get_cpu_percent() -> float | None:
    """Compute CPU usage percentage since last call.

    Uses /proc/self/stat fields 14 (utime) and 15 (stime) in clock ticks.
    Returns None on first call (no delta yet) or on non-Linux.
    """
    global _prev_cpu_time, _prev_wall_time

    content = _read_file("/proc/self/stat")
    if not content:
        return None

    # Fields are space-separated; field 2 (comm) may contain spaces and is
    # enclosed in parens, so split after the closing paren.
    try:
        after_comm = content[content.rindex(")") + 2 :]
        fields = after_comm.split()
        # utime = field index 11 (0-based after comm), stime = 12
        utime = int(fields[11])
        stime = int(fields[12])
    except (ValueError, IndexError):
        return None

    ticks_per_sec = os.sysconf("SC_CLK_TCK")
    cpu_seconds = (utime + stime) / ticks_per_sec
    wall_time = time.monotonic()

    if _prev_cpu_time is None:
        _prev_cpu_time = cpu_seconds
        _prev_wall_time = wall_time
        return None

    dt = wall_time - _prev_wall_time
    if dt <= 0:
        return 0.0

    cpu_pct = ((cpu_seconds - _prev_cpu_time) / dt) * 100.0
    _prev_cpu_time = cpu_seconds
    _prev_wall_time = wall_time
    return round(cpu_pct, 1)


def _get_cpu_limit_millicores() -> int | None:
    """Read container CPU limit from cgroup v2 or v1.

    Returns limit in millicores (e.g. 500 = 500m = 0.5 CPU).
    """
    # cgroup v2: cpu.max contains "quota period"
    content = _read_file("/sys/fs/cgroup/cpu.max")
    if content:
        parts = content.strip().split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                quota = int(parts[0])
                period = int(parts[1])
                if period > 0:
                    return int(quota * 1000 / period)
            except ValueError:
                pass

    # cgroup v1
    quota_str = _read_file("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period_str = _read_file("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota_str and period_str:
        try:
            quota = int(quota_str.strip())
            period = int(period_str.strip())
            if quota > 0 and period > 0:
                return int(quota * 1000 / period)
        except ValueError:
            pass

    return None


def _parse_env_millicores(env_var: str) -> int | None:
    """Parse a K8s Downward API CPU resource env var to millicores.

    The value is injected as a plain integer string representing the
    number of millicores (e.g. "50" for 50m, "1000" for 1 CPU).
    Kubernetes resourceFieldRef with divisor=1 gives the raw integer.
    """
    raw = os.environ.get(env_var)
    if not raw:
        return None
    try:
        # K8s injects CPU as a plain integer (millicores) by default
        return int(raw.strip())
    except ValueError:
        return None


def _parse_env_megabytes(env_var: str) -> float | None:
    """Parse a K8s Downward API memory resource env var to megabytes.

    The value is injected as a plain integer string representing bytes.
    """
    raw = os.environ.get(env_var)
    if not raw:
        return None
    try:
        return round(int(raw.strip()) / (1024 * 1024), 1)
    except ValueError:
        return None


def get_resource_snapshot() -> dict:
    """Return a snapshot of process resource usage.

    Returns a dict with:
      - rss_mb: Resident Set Size in MB
      - rss_limit_mb: Container memory limit in MB (or null)
      - rss_pct: RSS as percentage of limit (or null)
      - cpu_pct: CPU usage percentage since last call (or null on first call)
      - cpu_limit_mc: CPU limit in millicores (or null)
      - cpu_request_mc: CPU request in millicores (from K8S_CPU_REQUEST env, or null)
      - mem_request_mb: Memory request in MB (from K8S_MEM_REQUEST env, or null)
    """
    mem = _parse_proc_status()
    rss_kb = mem.get("rss_kb", 0)
    rss_mb = round(rss_kb / 1024, 1)

    mem_limit_kb = _get_memory_limit_kb()
    rss_limit_mb = round(mem_limit_kb / 1024, 1) if mem_limit_kb else None
    rss_pct = round((rss_kb / mem_limit_kb) * 100, 1) if mem_limit_kb and mem_limit_kb > 0 else None

    cpu_pct = _get_cpu_percent()
    cpu_limit_mc = _get_cpu_limit_millicores()

    # K8s Downward API env vars (set via resourceFieldRef in deployment.yaml)
    cpu_request_mc = _parse_env_millicores("K8S_CPU_REQUEST")
    mem_request_mb = _parse_env_megabytes("K8S_MEM_REQUEST")

    return {
        "rss_mb": rss_mb,
        "rss_limit_mb": rss_limit_mb,
        "rss_pct": rss_pct,
        "cpu_pct": cpu_pct,
        "cpu_limit_mc": cpu_limit_mc,
        "cpu_request_mc": cpu_request_mc,
        "mem_request_mb": mem_request_mb,
    }
