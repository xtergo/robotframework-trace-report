# Requirements Document

## Introduction

The RF Trace Viewer header includes a Logo_Slot at the far left, implemented in the header-status-diagnostics feature. Currently, no mechanism exists to populate this slot with an actual logo image. This feature adds a default SVG logo that ships with the viewer, allows operators to supply a custom SVG logo via Kubernetes configuration, and wires the logo through both the static report generator and the live-mode server so the Logo_Slot renders the correct image in all deployment modes.

Only SVG format is supported to ensure crisp rendering at any resolution without increasing bundle size with raster assets.

## Glossary

- **Logo_Slot**: The reserved `<img>` element at the left edge of the Viewer_Header, rendered by the App_Module when `window.__RF_LOGO_URL__` is set.
- **Default_Logo**: A built-in SVG file (`default-logo.svg`) shipped in the `viewer/` asset directory, used when no custom logo is configured.
- **Custom_Logo**: An operator-supplied SVG file that replaces the Default_Logo in the header.
- **App_Module**: The `app.js` IIFE that builds the DOM structure, header, and initializes views.
- **Trace_Report_Server**: The Python HTTP server (`server.py`) that serves the trace viewer UI and API endpoints.
- **Report_Generator**: The `generator.py` module that produces self-contained HTML reports with all assets inlined.
- **Kustomize_Base**: The base Kustomize manifests in `deploy/kustomize/base/` defining the core K8s resources.
- **AppConfig**: The Python configuration dataclass in `config.py` that merges CLI args, config file, and environment variables.
- **Logo_Endpoint**: An HTTP endpoint on the Trace_Report_Server that serves the active logo SVG file.

## Requirements

### Requirement 1: Default Logo Asset

**User Story:** As a user, I want the RF Trace Viewer to display a default logo in the header, so that the tool has a recognizable identity out of the box.

#### Acceptance Criteria

1. THE Report_Generator SHALL include a Default_Logo SVG file at `src/rf_trace_viewer/viewer/default-logo.svg`.
2. THE Default_Logo SHALL be a valid SVG document with a `viewBox` attribute for scalable rendering.
3. WHEN no Custom_Logo is configured, THE App_Module SHALL render the Default_Logo in the Logo_Slot.

### Requirement 2: Logo Serving in Live Mode

**User Story:** As a user running the viewer in live mode, I want the server to serve the active logo at a dedicated endpoint, so that the viewer can load the logo without embedding it in the HTML.

#### Acceptance Criteria

1. THE Trace_Report_Server SHALL expose a `GET /logo.svg` endpoint that returns the active logo file with `Content-Type: image/svg+xml`.
2. WHEN a Custom_Logo path is configured, THE `/logo.svg` endpoint SHALL serve the Custom_Logo file.
3. WHEN no Custom_Logo path is configured, THE `/logo.svg` endpoint SHALL serve the Default_Logo file.
4. THE Trace_Report_Server SHALL set `window.__RF_LOGO_URL__` to `/logo.svg` in the served HTML page so the App_Module renders the logo in the Logo_Slot.

### Requirement 3: Logo Embedding in Static Reports

**User Story:** As a user generating a static HTML report, I want the logo to be embedded inline, so that the report remains fully self-contained with no external dependencies.

#### Acceptance Criteria

1. WHEN generating a static report, THE Report_Generator SHALL embed the active logo as an inline SVG data URI in the `window.__RF_LOGO_URL__` variable.
2. WHEN a Custom_Logo path is provided via CLI or config, THE Report_Generator SHALL read and embed the Custom_Logo file.
3. WHEN no Custom_Logo path is provided, THE Report_Generator SHALL embed the Default_Logo file.
4. IF the configured Custom_Logo file does not exist, THEN THE Report_Generator SHALL exit with a non-zero exit code and a message identifying the missing file.
5. IF the configured Custom_Logo file is not a valid SVG (does not contain an `<svg` tag), THEN THE Report_Generator SHALL exit with a non-zero exit code and a message describing the validation failure.

### Requirement 4: Custom Logo Configuration

**User Story:** As a developer or operator, I want to configure a custom logo via CLI argument, config file, or environment variable, so that I can brand the viewer for my organization using the existing configuration system.

#### Acceptance Criteria

1. THE AppConfig SHALL accept a `logo_path` setting specifying the file path to a custom SVG logo.
2. THE `logo_path` setting SHALL follow the existing three-tier configuration precedence: CLI args > config file > environment variables.
3. THE AppConfig SHALL accept the `logo_path` value from the `LOGO_PATH` environment variable.
4. WHEN `logo_path` is not set, THE Trace_Report_Server and Report_Generator SHALL use the Default_Logo.

### Requirement 5: Kubernetes Logo Configuration

**User Story:** As a cluster operator deploying the viewer via Kustomize, I want to provide a custom logo through Kubernetes configuration, so that the viewer displays my organization's branding without modifying the container image.

#### Acceptance Criteria

1. THE Kustomize_Base SHALL include a commented-out ConfigMap named `trace-report-logo` with a `LOGO_PATH` data entry and a volume mount example for supplying a custom SVG file.
2. THE Kustomize_Base SHALL include commented-out volume and volumeMount definitions in the Deployment that mount the logo ConfigMap at a known path (e.g. `/etc/trace-report/logo/`).
3. WHEN the `LOGO_PATH` environment variable is set in the container, THE Trace_Report_Server SHALL use the file at that path as the Custom_Logo.
4. WHEN the `LOGO_PATH` environment variable is not set, THE Trace_Report_Server SHALL use the Default_Logo.

### Requirement 6: SVG Format Validation

**User Story:** As a developer, I want the system to validate that logo files are SVG format, so that unsupported image formats are rejected early with a clear error message.

#### Acceptance Criteria

1. WHEN a `logo_path` is configured, THE Trace_Report_Server SHALL validate at startup that the file exists and contains an `<svg` tag.
2. IF the configured logo file does not exist at startup, THEN THE Trace_Report_Server SHALL log a warning and fall back to the Default_Logo.
3. IF the configured logo file is not a valid SVG at startup, THEN THE Trace_Report_Server SHALL log a warning and fall back to the Default_Logo.

### Requirement 7: Logo Display Constraints

**User Story:** As a user, I want the logo to render at a consistent size in the header, so that it looks clean regardless of the source SVG dimensions.

#### Acceptance Criteria

1. THE App_Module SHALL render the logo image with a maximum height equal to the Viewer_Header height.
2. THE App_Module SHALL preserve the logo aspect ratio using CSS.
3. THE logo `<img>` element SHALL have an `alt` attribute set to the value of `window.__RF_LOGO_ALT__` if provided, or "Logo" as the default when a logo is displayed.

### Requirement 8: Backward Compatibility

**User Story:** As an existing user, I want the logo feature to be additive, so that current deployments without logo configuration continue to work without changes.

#### Acceptance Criteria

1. WHEN no `logo_path` is configured and no `window.__RF_LOGO_URL__` is set by external means, THE App_Module SHALL render the Default_Logo in the Logo_Slot.
2. THE existing `window.__RF_LOGO_URL__` and `window.__RF_LOGO_ALT__` override mechanism SHALL continue to work, taking precedence over the default logo behavior.
3. THE existing CLI commands (`rf-trace-report static`, `rf-trace-report serve`) SHALL retain their current behavior when `logo_path` is not provided.
4. THE `pip install` package SHALL include the Default_Logo SVG file as part of the viewer assets.
