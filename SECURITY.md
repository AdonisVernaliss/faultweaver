# Security policy

Faultweaver is pre-release security-assessment software for explicitly authorized
targets. Automated observations are hypotheses; operators decide what becomes a
confirmed Finding. Do not use it without permission or to perform destructive work.

## Local trust boundary

The workspace/API is a **single-operator local application without login or
multi-user isolation**. Keep both services on loopback. Anyone who can access the
unlocked API can read assessment data or invoke its scoped workflows. CORS, CSP
and encryption at rest are not substitutes for authentication. A reverse proxy
does not make public deployment supported. Do not run multiple API workers against
one database or expose the application to an untrusted network.

SQLCipher encrypts and authenticates database pages and indexes. The independently
stored key is required before database opening; missing/wrong keys fail closed.
This protects a copied database **without its key**, not a compromised running
backend, host administrator, memory inspection, rollback or possession of both
assets. Key loss is unrecoverable. See [storage and recovery](docs/secret-storage.md).

## Untrusted traffic and exports

Scope enforcement applies immediately before outbound requests and redirect hops.
The crawler uses bounded anonymous GET requests, does not submit forms or execute
JavaScript, and never treats discovery as authorization. Imports are inert data;
cURL is not executed and external OpenAPI references are not fetched.

Recognized credential fields, authorization headers and session values are
redacted in ordinary API/UI/Evidence representations. Arbitrary prose and
application content may still be confidential: redaction is not a general PII or
secret classifier. Retained replay material remains accessible to the unlocked
backend and must not be copied into public diagnostics.

Report HTML uses escaped plain text, an offline restrictive CSP, no scripts or
external assets and a sandboxed preview. Markdown escapes prose; captured target
content is fenced. JSON is data, not safe HTML. Treat **every downloaded report,
HAR, screenshot and legacy plaintext backup as sensitive**, even when redacted.
Exports are deliberately outside encrypted database storage. Review before sharing;
do not publish private evidence or rely on automatic forensic deletion.

## Local demonstration targets

Northstar Billing and the four optional compatibility labs are intentionally
vulnerable, disabled/separate by default and published on loopback only. Never
expose them to a LAN or the internet. Demo credentials are public synthetic
fixtures, not defaults for any real service. No target-specific production logic
or exploit automation is required for compatibility validation.

## Reporting a Faultweaver vulnerability

No public release or private disclosure endpoint is established yet. Do not
publish sensitive reports, credentials or target data in public issues. Retain a
minimal sanitized reproduction locally until the maintainer provides a verified
private contact route. The [local release audit](docs/full-release-audit.md)
records development verification, not independent third-party assurance, an SLA,
a supported-version policy or a vulnerability-free release.
