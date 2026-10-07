# Baseline assessments

Faultweaver baseline assessments turn one explicitly authorized URL into a
bounded set of HTTP exchanges, discovered routes, passive observations, and
conservative candidates. They are an inventory and triage aid, not an aggressive
scanner and not evidence that a vulnerability is confirmed.

## Request boundary

- Only `http` and `https` targets are accepted. Fragments are removed and URL
  user information is rejected.
- URL identity normalizes scheme, IDN hostname, IPv4/IPv6 host syntax, default
  ports, dot segments, unreserved percent escapes, and fragments while keeping
  meaningful trailing slashes and query ordering.
- The engagement's existing exact scheme, hostname, effective port, and path
  prefix matcher runs before the seed request, every discovered URL, and every
  redirect destination.
- Out-of-scope links and redirects are persisted as `skipped`; they never enter
  the request scheduler. Scope never expands from page content, redirects,
  `robots.txt`, or sitemaps.
- TLS verification uses the HTTP client's secure default. There is no insecure
  mode in this milestone.

## Crawl behavior and limits

The explicit breadth-first frontier records `discovered`, `queued`, `requested`,
`skipped`, and `failed` states. It deduplicates canonical URLs, enforces depth and
query-variation caps, and cannot recurse outside the scheduler. The centralized
rate limiter controls request starts and the bounded worker pool enforces the
configured concurrency.

Stored discovery metadata is additionally capped at `min(10000, max_requests * 20)`
unique URLs per run, including skipped links. Further links are omitted with a
warning; the network request limit alone is not a metadata-size limit.

Default limits are 50 HTML pages, depth 3, 75 total requests, 1 request/second,
concurrency 2, a 10 second request timeout, 1 MB response capture, and 3 query
variants per path. The operator can adjust them within fixed API bounds. A run
uses anonymous `GET` only. It records links, scripts, images, frames, media, and
forms, but automatically requests only navigational pages, frames, redirects,
and bounded site metadata. Form action, method, encoding, and input name/type/
hidden/value-presence metadata is stored; no form is submitted. Binary responses
retain status, headers, timing, and truncation metadata without a body copy.
Response cookies are never attached to subsequent baseline requests. Ambient
proxy and netrc settings do not supply hidden authentication or routes.

`robots.txt`, sitemap locations, and disallowed paths are discovery metadata,
not authorization. JavaScript is not executed and no browser crawler, shell,
`curl`, `wget`, `nmap`, `nikto`, or similar program is invoked.

Stop prevents new frontier work and lets the small bounded in-flight set finish.
Partial requests, discoveries, observations, and candidates remain available.
Individual request errors mark that item failed and do not fail the entire run.
On startup, stale Pending or Running records become Stopped with an interrupted-
restart reason; work never resumes invisibly.

## Passive checks

Checks are isolated modules with stable IDs, an explanation, applicability,
confidence, classification, and suggested severity. Signals are grouped by run,
check, and host to limit noise. Every affected exchange remains linked.

| Check family | Informational observation | Candidate condition |
| --- | --- | --- |
| Response headers | Context-aware missing defensive headers; HSTS is considered only on HTTPS HTML | Missing CSP on an HTML response |
| Cookies | None | Session/auth-like cookie without `HttpOnly`, or an HTTPS cookie without `Secure` |
| Disclosure | Version-bearing `Server` or `X-Powered-By` banner | A naturally occurring 5xx response containing a stack-trace marker |
| Redirects | External origin redirect, explicitly not an open-redirect claim; canonical self-redirect | HTTPS-to-HTTP downgrade |
| Forms | Cross-origin form action | Password form whose action uses HTTP |
| Transport | None; resource references remain inventory metadata | HTTP resource referenced by an HTTPS page |
| Cache policy | Authentication-sensitive URL or cookie context without an explicit `no-store` directive | None; application-specific cache behavior stays informational |
| Content metadata | Internal filesystem path pattern, or sensitive-looking JSON field names without copying their values | None; content context requires manual review |

Missing-header observations are not blanket vulnerability claims. Cache behavior,
error responses, cookies, and transport signals require application context.
Faultweaver never auto-confirms or assigns an `FW-###` identifier. Candidate
promotion remains an explicit operator action with operator-authored finding
description, impact, reproduction, and remediation.

## Persistence and provenance

Crawler traffic uses the existing `HttpExchange` store with source `crawler`,
run ID, depth, parent exchange, discovery kind, and optional failure reason.
Attack Surface receives `crawler` provenance for discovered and observed routes;
multi-source endpoints retain all sources. Baseline candidates extend the
existing Candidate workflow and link the originating run, stable check ID,
endpoint, affected exchanges, reasoning, confidence, and suggested severity.

Response bodies and credential-bearing headers are sensitive local assessment
data. Public API serializers and the UI redact recognized credentials and known
credential reflections. The database and indexes use independently keyed
SQLCipher storage; filesystem protection and separate key custody are still
required. See [storage and recovery](secret-storage.md). Redaction does not make
arbitrary response data or exported reports public.
