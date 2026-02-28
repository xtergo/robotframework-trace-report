"""Pure helper functions for OCI & Flux verification scripts.

These functions encapsulate testable logic used by verify-oci.sh and
verify-flux.sh, enabling property-based and unit testing without
requiring a running cluster.

Requirements: 2.2, 2.7, 3.4, 4.4, 6.1, 6.4
"""

import re
import textwrap

# The GHCR image pattern used in Kustomize manifests
_GHCR_IMAGE_RE = re.compile(r"ghcr\.io/xtergo/robotframework-trace-report:[^\s\"']+")
_GHCR_IMAGE_BASE = "ghcr.io/xtergo/robotframework-trace-report"


def substitute_image_tag(manifest: str, tag: str) -> str:
    """Replace the GHCR image reference in a manifest with the given tag.

    Finds all occurrences of ``ghcr.io/xtergo/robotframework-trace-report:<anything>``
    and replaces them with ``ghcr.io/xtergo/robotframework-trace-report:<tag>``.

    Args:
        manifest: Kustomize manifest string (may be multi-document YAML).
        tag: Image tag to substitute (e.g. ``0.1.0``, ``sha-abc1234``, ``latest``).

    Returns:
        The manifest with all GHCR image references updated.
    """
    return _GHCR_IMAGE_RE.sub(f"{_GHCR_IMAGE_BASE}:{tag}", manifest)


def generate_git_repo_yaml(ref: str) -> str:
    """Return a Flux GitRepository CR YAML string for the given git ref.

    Args:
        ref: Git reference (branch name or tag).

    Returns:
        A YAML string defining a GitRepository custom resource.
    """
    return textwrap.dedent(f"""\
        apiVersion: source.toolkit.fluxcd.io/v1
        kind: GitRepository
        metadata:
          name: trace-report
          namespace: flux-system
        spec:
          interval: 1m
          url: https://github.com/xtergo/robotframework-trace-report
          ref:
            branch: {ref}
    """)


def format_summary(passed: bool, elapsed: int) -> str:
    """Return a formatted summary line with pass/fail status and elapsed time.

    Args:
        passed: Whether the verification passed.
        elapsed: Elapsed time in seconds.

    Returns:
        A summary string like ``✓ Verification passed in 42s``
        or ``✗ Verification failed in 42s``.
    """
    icon = "✓" if passed else "✗"
    status = "passed" if passed else "failed"
    return f"{icon} Verification {status} in {elapsed}s"


def cluster_name(verify_type: str) -> str:
    """Return the kind cluster name for a verification type.

    Args:
        verify_type: Either ``"oci"`` or ``"flux"``.

    Returns:
        The cluster name (``oci-verify`` or ``flux-verify``).

    Raises:
        ValueError: If *verify_type* is not ``"oci"`` or ``"flux"``.
    """
    names = {
        "oci": "oci-verify",
        "flux": "flux-verify",
    }
    if verify_type not in names:
        raise ValueError(f"Unknown verify_type {verify_type!r}, expected 'oci' or 'flux'")
    return names[verify_type]
