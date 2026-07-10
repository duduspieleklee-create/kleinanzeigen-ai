# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Changelog tracking for kleinanzeigen-ai.

### Changed
- Worker seller-info extraction now caches listing detail page HTML within one task runtime, reducing duplicate HTTP requests across repeated seller URLs. Added retry wrapper for flaky fetch/no-data paths and Sentry metrics for request count, cache hits, request duration, no-match occurrences, and fetch failures.
