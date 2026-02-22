# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure and documentation
- Architecture design document
- Development roadmap (TODO.md)
- Timeline Gantt chart with zoom and pan capabilities
- Debug API for timeline state inspection (`window.RFTraceViewer.debug.timeline`)
- Comprehensive documentation for timeline rendering issue and testability improvements

### Fixed
- Timeline rendering: Added missing `start_time` and `end_time` timestamps to RF model dataclasses
- Timeline canvas now dynamically sizes based on content to prevent span clipping
- Timeline section now scrollable when content exceeds container height
