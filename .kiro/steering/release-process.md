---
inclusion: auto
---

# Release Process

## Version Bump Before Tagging

When creating a new release, the version bump commit **must** be part of the tagged commit. Never create a tag or GitHub release before the version string is updated in source.

### Correct order

1. Bump `version` in `pyproject.toml` and `__version__` in `src/rf_trace_viewer/__init__.py`
2. Commit: `chore: bump version to X.Y.Z`
3. Create the git tag on that commit: `git tag vX.Y.Z`
4. Push tag: `git push origin vX.Y.Z`
5. Create the GitHub release: `gh release create vX.Y.Z --title "vX.Y.Z" --notes "..."`

### Why this matters

- The `publish-oci.yml` workflow triggers on `release: published` and builds the Docker image from the tagged commit.
- If the tag points to a commit before the version bump, the published GHCR image will contain the old version string in both the Python package metadata and the UI (`window.__RF_VERSION__`).
- Fixing this after the fact requires force-moving the tag, deleting the release, and recreating it — avoidable overhead.

### Quick checklist

- [ ] `pyproject.toml` `version` matches the release tag
- [ ] `src/rf_trace_viewer/__init__.py` `__version__` matches the release tag
- [ ] Tag is created on the version bump commit (not before it)
- [ ] GitHub release is created after the tag is pushed

### Files that contain the version

- `pyproject.toml` — `version = "X.Y.Z"` (package metadata, PyPI)
- `src/rf_trace_viewer/__init__.py` — `__version__ = "X.Y.Z"` (runtime, injected into UI via `server.py`)
