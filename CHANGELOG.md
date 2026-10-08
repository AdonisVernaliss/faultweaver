# Changelog

## Unreleased

## [1.0.0-rc.1] - 2026-10-08

First public release candidate. Intended for one trusted local operator performing
explicitly authorized assessments; not a stable release or a hosted service.

### Added

- Engagement-scoped URL baselines, bounded anonymous discovery, and inert raw
  HTTP, HAR, cURL, and OpenAPI imports.
- Request Explorer, observed and declared Attack Surface entries, scoped replay,
  identity-aware response comparison, and an authorization matrix.
- Reviewed Candidates, manual Findings, immutable Evidence, operator-authored
  Attack Chains, and separate Retests with preserved verification history.
- Report drafts, stable identifiers, immutable revisions, and offline HTML,
  Markdown, and schema-versioned JSON exports.
- Optional Northstar Billing demo and documented workflow compatibility with
  Juice Shop 20.2.0, DVWA 2.5, WebGoat 2026.4, and Mutillidae II 2.12.8.

### Security

- SQLCipher-protected database storage with separately supplied local keys,
  explicit legacy migration, and fail-closed handling of missing or incorrect keys.
- Backend-enforced URL scope and redirect checks, conservative automation,
  credential redaction, Evidence ownership checks, and bounded imports.
- Escaped offline reports, restrictive content security policies, allowlisted
  build inputs, and synthetic test keys independent of operator storage.
- Private vulnerability reporting through the repository's Security tab.

### Changed

- Added public Docker setup instructions, storage recovery guidance, synthetic
  screenshots, reporting documentation, and explicit operational limitations.
- Corrected selection races and accelerated exact response text comparisons
  without changing matching results or Candidate thresholds.

[1.0.0-rc.1]: https://github.com/AdonisVernaliss/faultweaver/releases/tag/v1.0.0-rc.1
