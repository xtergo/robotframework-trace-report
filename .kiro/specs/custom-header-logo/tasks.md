# Implementation Plan: Custom Header Logo

## Overview

Add logo support to the RF Trace Viewer header. A default SVG ships with the package and renders in the Logo_Slot. Operators can override it via `logo_path` (CLI / config file / `LOGO_PATH` env var). The logo is served at `/logo.svg` in live mode and embedded as a data URI in static reports. Kustomize base gets a commented-out ConfigMap example.

Changes touch `config.py`, `cli.py`, `server.py`, `generator.py`, `app.js`, Kustomize manifests, and `pyproject.toml`. One new asset file: `default-logo.svg`.

## Tasks

- [x] 1. Add default logo asset and package configuration
  - [x] 1.1 Move `logo/default.svg` to `src/rf_trace_viewer/viewer/default-logo.svg`
    - The user has provided the default logo at `logo/default.svg` in the project root
    - Move and rename it to the target location; verify it has a valid `viewBox` attribute
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Update `pyproject.toml` package-data to include `*.svg` files
    - Add `"viewer/*.svg"` to the `rf_trace_viewer` package-data glob
    - _Requirements: 8.4_

- [x] 2. Implement `logo_path` configuration and SVG validation
  - [x] 2.1 Add `logo_path` field to `AppConfig` in `src/rf_trace_viewer/config.py`
    - Add `logo_path: str | None = None` to the dataclass
    - Add `LOGO_PATH` to the `env_map` in `load_config()`
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 2.2 Add `validate_svg(path)` function to `src/rf_trace_viewer/config.py`
    - Returns `tuple[bool, str]` — `(True, "")` on success, `(False, reason)` on failure
    - Check file existence and presence of `<svg` tag in content
    - _Requirements: 6.1_

  - [x] 2.3 Add `--logo-path` argument to `_add_shared_arguments()` in `src/rf_trace_viewer/cli.py`
    - Maps to `logo_path` in the CLI dict via existing argparse conversion
    - _Requirements: 4.1, 4.2_

  - [ ]* 2.4 Write property test for SVG validation correctness (Property 4)
    - **Property 4: SVG validation correctness**
    - **Validates: Requirements 6.1**
    - Test in `tests/unit/test_logo.py`
    - Generate random strings with/without `<svg` tag; verify `validate_svg` returns `True` iff content contains `<svg`

  - [ ]* 2.5 Write property test for configuration precedence (Property 3)
    - **Property 3: Configuration precedence for logo_path**
    - **Validates: Requirements 4.2, 4.3**
    - Test in `tests/unit/test_logo.py`
    - Generate 3 distinct strings for CLI, config file, env var; verify precedence: CLI > config > env

- [x] 3. Implement logo serving in live mode (`server.py`)
  - [x] 3.1 Add logo resolution at startup in `LiveServer.__init__`
    - Accept `logo_path` from config; call `validate_svg` if set
    - On validation failure, log warning and fall back to default logo
    - Store resolved path as `self.logo_path`
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 3.2 Add `GET /logo.svg` endpoint in `_do_GET`
    - Serve the file at `self.server.logo_path` with `Content-Type: image/svg+xml`
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Inject `window.__RF_LOGO_URL__ = "/logo.svg"` in `_serve_viewer`
    - Add to the script block in the served HTML page
    - _Requirements: 2.4_

  - [ ]* 3.4 Write property test for server graceful fallback (Property 5)
    - **Property 5: Server graceful fallback on invalid logo**
    - **Validates: Requirements 6.2, 6.3**
    - Test in `tests/unit/test_logo.py`
    - Generate non-existent or non-SVG paths; verify resolved path is the default logo

  - [ ]* 3.5 Write unit tests for logo endpoint
    - Test `/logo.svg` returns correct content type and default logo content
    - Test `_serve_viewer` HTML includes `window.__RF_LOGO_URL__`
    - _Requirements: 2.1, 2.3, 2.4_

- [x] 4. Checkpoint — Server logo support complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement logo embedding in static reports (`generator.py`)
  - [x] 5.1 Add `logo_path` field to `ReportOptions` in `src/rf_trace_viewer/generator.py`
    - `logo_path: str | None = None`
    - _Requirements: 3.2_

  - [x] 5.2 Implement logo resolution and embedding in `generate_report()`
    - If `logo_path` set, validate with `validate_svg`; on failure, print error and `sys.exit(1)`
    - If `logo_path` not set, use default logo from `_VIEWER_DIR / "default-logo.svg"`
    - Read SVG, base64-encode to `data:image/svg+xml;base64,...` URI
    - Inject `window.__RF_LOGO_URL__ = "<data URI>"` into the HTML script block
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.3 Wire `logo_path` from CLI config to `ReportOptions` in the static report command
    - Pass `config.logo_path` through to `ReportOptions` when building the report
    - _Requirements: 4.1, 4.2_

  - [ ]* 5.4 Write property test for logo embedding round-trip (Property 1)
    - **Property 1: Logo embedding round-trip**
    - **Validates: Requirements 3.1, 3.2**
    - Test in `tests/unit/test_logo.py`
    - Generate random valid SVG strings; base64-encode to data URI, decode, compare byte-for-byte

  - [ ]* 5.5 Write property test for generator rejects invalid logo (Property 2)
    - **Property 2: Generator rejects invalid logo files**
    - **Validates: Requirements 3.4, 3.5**
    - Test in `tests/unit/test_logo.py`
    - Generate non-existent paths and non-SVG content; verify generator validation returns failure

- [x] 6. Checkpoint — Static report logo support complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update App Module (`app.js`) for logo display
  - [x] 7.1 Update Logo_Slot rendering in `_initApp` in `src/rf_trace_viewer/viewer/app.js`
    - When `window.__RF_LOGO_URL__` is set, render `<img>` in Logo_Slot
    - Set `alt` to `window.__RF_LOGO_ALT__` if defined, otherwise `"Logo"`
    - Apply CSS: `max-height` equal to header height, `object-fit: contain` for aspect ratio
    - _Requirements: 1.3, 7.1, 7.2, 7.3, 8.1, 8.2_

  - [ ]* 7.2 Write unit tests for logo display behavior
    - Test default alt text is `"Logo"` when `__RF_LOGO_ALT__` is not set
    - Test external `__RF_LOGO_URL__` override still works
    - Test backward compatibility when no logo config is present
    - _Requirements: 7.3, 8.1, 8.2_

- [ ] 8. Add Kustomize logo configuration examples
  - [ ] 8.1 Add commented-out logo ConfigMap and volume mount to `deploy/kustomize/base/deployment.yaml`
    - Add commented-out `volume` referencing `trace-report-logo` ConfigMap
    - Add commented-out `volumeMount` at `/etc/trace-report/logo/`
    - Add commented-out `LOGO_PATH` env var pointing to the mounted file
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 8.2 Create commented-out `deploy/kustomize/base/logo-configmap.yaml` example
    - Show how to create the ConfigMap from a custom SVG file
    - _Requirements: 5.1_

- [ ] 9. Final checkpoint — All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- All tests go in `tests/unit/test_logo.py`
- Property tests use Hypothesis with dev/ci profiles — no hardcoded `@settings`
- All tests run in Docker via `make test-unit` (dev profile) or `make test-full` (ci profile)
- Checkpoints at tasks 4, 6, and 9 ensure incremental validation
