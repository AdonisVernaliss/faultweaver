# Architecture

Faultweaver is a local-first monorepo with two core runtime services, one
persistent data store, and an opt-in stateless demonstration target.

```text
Browser
  -> SvelteKit workspace and same-origin API proxy
       -> FastAPI application
            -> engagement and scope domains
            -> engagement-scoped identity contexts
            -> bounded HAR, cURL, OpenAPI, and raw HTTP import adapters
            -> canonical HTTP traffic and normalized Attack Surface repository
            -> bounded scoped crawler and modular passive baseline checks
            -> scope-gated replay client
            -> response normalization, structured diff, and candidate analysis
            -> finding, immutable evidence, operator note, and retest lifecycle
            -> ordered, operator-authored attack chain composition
            -> canonical report drafts, immutable revisions and offline renderers
            -> authenticated SQLCipher (SQLite-compatible)

Optional local validation profile
  -> deterministic, deliberately vulnerable demo SaaS
       -> read-only tenant and audit fixtures
       -> no outbound client or persistent state
```

## Backend boundaries

- `engagements` owns engagement metadata and lifecycle state.
- `scope` normalizes and compares scheme, hostname, effective port, and canonical path prefixes.
- `imports` parses bounded untrusted documents into canonical HTTP records or
  declared endpoints before persistence. cURL input is never passed to a shell;
  OpenAPI servers remain metadata and external references are never fetched.
- `http_traffic` parses imported requests, stores request/response records, renders raw requests, and performs replay.
- `assessments` owns `RUN-###` lifecycle, canonical URL identity, the explicit
  breadth-first frontier, centralized scheduling/rate limiting, HTML/form/XML
  discovery, bounded HTTP capture, run recovery, and modular passive checks.
- `identities` owns local authentication contexts and applies them only within their engagement.
- `analysis` normalizes bounded responses, stores explainable comparisons, derives the authorization matrix, and emits conservative candidates.
- `findings` owns explicit candidate promotion, stable display IDs, report prose, immutable evidence snapshots, operator notes, retest attempts, and append-only lifecycle events.
- `attack_chains` owns engagement-scoped `AC-###` identifiers, narrative impact, ordered steps, evidence references, explicit validation, archival, and append-only lifecycle events.
- `reports` owns `REP-###` drafts, consistent canonical snapshots and immutable
  revisions rendered as HTML/Markdown/JSON; it never reads raw HTTP/Identity data.
- `storage` owns independent keys, authenticated database opening, process locks
  and explicit offline legacy conversion. Schema `0007` records encrypted storage
  policy; `0008` adds Reports/revisions and a per-Engagement Report counter.

Every replay URL is checked in the networking layer before a request is sent. Redirects are handled one hop at a time and checked before following. Sensitive authorization and cookie headers are removed if a redirect changes origin. Response capture is bounded to one megabyte by default.

Packaged Alembic migrations run on startup. The baseline revision can adopt the original pre-migration schema after validating every expected table and column; revisions `0002` through `0006` evolve identity/analysis, finding-lifecycle, Attack Chain, import-batch, Attack Surface, and baseline assessment data without dropping stored engagements or traffic. Revision `0005` links existing exchanges to conservatively backfilled exact-path endpoints; revision `0006` adds run/discovery/form/observation state and nullable crawler provenance to the canonical HTTP and Candidate records.

## Frontend boundaries

The SvelteKit application is a client-rendered local workspace. Its server route proxies `/api` to the configured FastAPI service so local and Compose deployments have one browser origin. Assessment Runs presents bounded configuration, concrete live counters, graceful Stop, and persisted run sections while linking to the canonical Request Explorer and Candidate views. The unified import dialog requires a redacted preview before persisting HAR, cURL, or OpenAPI input. Attack Surface presents normalized endpoint provenance and declared/discovered/observed state; Request Explorer retains every concrete transaction and can filter by source. Candidate review, finding report, evidence library, retest ledger, and Attack Chain builder remain distinct views in one continuous workflow.

## Attack Chain model

An Attack Chain is a deliberate operator-authored explanation of how confirmed issues combine into a larger outcome. It is not an automatically inferred vulnerability graph. A **Finding** step references an active Finding and surfaces its current identity, severity, and status; an **Intermediate** step records a meaningful transition that the operator can explain even when it is not itself a Finding. Integer positions define a deterministic order and are normalized after insertion, removal, or reordering.

Chains and individual steps may reference existing immutable Evidence records. These relationships do not copy or mutate evidence snapshots. A Finding can appear in more than one chain, and Finding detail exposes backlinks to every related chain.

Validation is explicit. A chain must have a title, at least two meaningful steps, contiguous unique positions, and valid active Finding references before it can become `Validated`. Editing its narrative or structure returns it to `Draft` so the revised path must be reviewed again. Archival is non-destructive: archived chains remain readable with their ordering, evidence links, and history, but can no longer be edited.

## Persistence

All tables and indexes described below are protected by SQLCipher, including
Report drafts and revision documents. The SQLite-compatible filename/URL is not
a plaintext-storage option. Keys are supplied outside the data volume. See
[storage](secret-storage.md) and [reporting](reporting.md) for lifecycle details.

SQLCipher is the source of truth. The default database is `data/faultweaver.db`;
Compose mounts `/data/faultweaver.db` from a named volume. Assessment runs retain
target, limits, status, counters, timestamps, warnings, frontier state, forms,
observations and candidate links. Import batches retain format, safe filename,
digest, counts, warnings and provenance. Imports/replays are separate records
linked through `parent_exchange_id`; crawler traffic adds run/depth/discovery
provenance to the same store. Comparisons link the original to both replays and
Identity contexts; Candidates remain linked after promotion. Per-Engagement
counters allocate `RUN-###`, `IMP-###`, `FW-###`, `EV-###`, `RT-###`, `AC-###` and
`REP-###` identifiers.

Attack Surface grouping is deliberately conservative. Observed traffic groups by exact method, origin, and concrete path. A concrete request is associated with a parameterized path only when an imported OpenAPI declaration for the same origin provides that template. Declared operations without a server remain useful standalone inventory rather than being guessed onto an observed host. Re-importing identical content warns about the probable duplicate but preserves its raw transactions and batch provenance.

Evidence stores a redacted point-in-time JSON snapshot rather than a live rendering of its source. Source edits, archival, or deletion therefore cannot change the captured evidence. Finding and retest relations distinguish original evidence from evidence selected for a particular retest. Identity and lifecycle deletion actions archive or restrict records instead of casually destroying historical context.

Replay credentials and imported request material remain in the local database. Public API serializers and the UI redact authorization, cookie, API-key, URL userinfo, sensitive query/fragment values, and common structured body secret fields by default. Normalized and comparison records are derived from redacted response material.

Every Identity custom-header value is sensitive. Replay headers carry immutable
sensitivity in existing encrypted JSON, so later Identity edits cannot expose
older credentials. Actual final-hop transport headers, including redirect cookies,
are retained. Legacy Identity replays fail closed; comparison and Evidence reads
apply defense-in-depth redaction without changing stored sources. Known-value
matching can also hide non-secret text equal to a credential.

## Safety defaults

- No outbound request is allowed without an active matching scope rule.
- Only HTTP and HTTPS targets are accepted.
- Redirects are not followed implicitly.
- Replay credentials and cookie-jar state are removed on origin changes; HTTP
  clients do not inherit ambient proxy or netrc configuration. Scope is a URL
  allowlist, not resolved-address pinning or a network firewall.
- Assessment redirects are represented as discoveries and scope-checked before
  they enter the request frontier; external destinations are never requested.
- The crawler uses only anonymous GET, never submits forms, never executes
  JavaScript, and does not invoke a browser, shell, cURL, or external scanner.
- Depth, pages, total requests, rate, concurrency, timeout, response capture,
  and query variants are explicit per-run limits.
- Request timeout, redirect count, and captured response size are bounded.
- Importing traffic parses and stores it but does not send it.
- HAR, cURL, and OpenAPI inputs are bounded and handled as untrusted data; no
  command execution or external reference fetch is part of import.
- Automated confirmation of vulnerabilities is outside this slice and will remain an explicit operator decision.
- Evidence snapshots and lifecycle history redact recognized replay credentials;
  arbitrary operator prose and target data can remain confidential.
- The demo target is disabled by default, published only on host loopback, and
  isolated from production persistence. Its non-loopback container bind requires
  an explicit environment override supplied only by the loopback-published
  Compose profile.
