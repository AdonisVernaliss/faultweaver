# Architecture

Faultweaver is a local-first monorepo with two runtime services and one persistent data store.

```text
Browser
  -> SvelteKit workspace and same-origin API proxy
       -> FastAPI application
            -> engagement and scope domains
            -> engagement-scoped identity contexts
            -> bounded HAR, cURL, OpenAPI, and raw HTTP import adapters
            -> canonical HTTP traffic and normalized Attack Surface repository
            -> scope-gated replay client
            -> response normalization, structured diff, and candidate analysis
            -> finding, immutable evidence, operator note, and retest lifecycle
            -> ordered, operator-authored attack chain composition
            -> SQLite
```

## Backend boundaries

- `engagements` owns engagement metadata and lifecycle state.
- `scope` normalizes and compares scheme, hostname, effective port, and canonical path prefixes.
- `imports` parses bounded untrusted documents into canonical HTTP records or
  declared endpoints before persistence. cURL input is never passed to a shell;
  OpenAPI servers remain metadata and external references are never fetched.
- `http_traffic` parses imported requests, stores request/response records, renders raw requests, and performs replay.
- `identities` owns local authentication contexts and applies them only within their engagement.
- `analysis` normalizes bounded responses, stores explainable comparisons, derives the authorization matrix, and emits conservative candidates.
- `findings` owns explicit candidate promotion, stable display IDs, report prose, immutable evidence snapshots, operator notes, retest attempts, and append-only lifecycle events.
- `attack_chains` owns engagement-scoped `AC-###` identifiers, narrative impact, ordered steps, evidence references, explicit validation, archival, and append-only lifecycle events.

Every replay URL is checked in the networking layer before a request is sent. Redirects are handled one hop at a time and checked before following. Sensitive authorization and cookie headers are removed if a redirect changes origin. Response capture is bounded to one megabyte by default.

Packaged Alembic migrations run on startup. The baseline revision can adopt the original pre-migration schema after validating every expected table and column; revisions `0002` through `0005` evolve identity/analysis, finding-lifecycle, Attack Chain, import-batch, and Attack Surface data without dropping stored engagements or traffic. Revision `0005` links existing exchanges to conservatively backfilled exact-path endpoints.

## Frontend boundaries

The SvelteKit application is a client-rendered local workspace. Its server route proxies `/api` to the configured FastAPI service so local and Compose deployments have one browser origin. The unified import dialog requires a redacted preview before persisting HAR, cURL, or OpenAPI input. Attack Surface presents normalized endpoint provenance and declared/observed state; Request Explorer retains every concrete transaction and can filter by source. Candidate review, finding report, evidence library, retest ledger, and Attack Chain builder remain distinct views in one continuous workflow.

## Attack Chain model

An Attack Chain is a deliberate operator-authored explanation of how confirmed issues combine into a larger outcome. It is not an automatically inferred vulnerability graph. A **Finding** step references an active Finding and surfaces its current identity, severity, and status; an **Intermediate** step records a meaningful transition that the operator can explain even when it is not itself a Finding. Integer positions define a deterministic order and are normalized after insertion, removal, or reordering.

Chains and individual steps may reference existing immutable Evidence records. These relationships do not copy or mutate evidence snapshots. A Finding can appear in more than one chain, and Finding detail exposes backlinks to every related chain.

Validation is explicit. A chain must have a title, at least two meaningful steps, contiguous unique positions, and valid active Finding references before it can become `Validated`. Editing its narrative or structure returns it to `Draft` so the revised path must be reviewed again. Archival is non-destructive: archived chains remain readable with their ordering, evidence links, and history, but can no longer be edited.

## Persistence

SQLite is the source of truth. The default local database is `data/faultweaver.db`; Compose mounts `/data/faultweaver.db` from a named volume. Import batches use stable engagement-scoped `IMP-###` IDs and retain format, safe filename, content digest, counts, warnings, and timestamps. Imported requests and replays are separate records linked through `parent_exchange_id`; observed requests also retain their batch, source entry, and normalized endpoint links. Comparisons link an immutable original to both replay records and their identity contexts; candidates remain linked after promotion. Per-engagement counters allocate stable `IMP-###`, `FW-###`, `EV-###`, `RT-###`, and `AC-###` display IDs.

Attack Surface grouping is deliberately conservative. Observed traffic groups by exact method, origin, and concrete path. A concrete request is associated with a parameterized path only when an imported OpenAPI declaration for the same origin provides that template. Declared operations without a server remain useful standalone inventory rather than being guessed onto an observed host. Re-importing identical content warns about the probable duplicate but preserves its raw transactions and batch provenance.

Evidence stores a redacted point-in-time JSON snapshot rather than a live rendering of its source. Source edits, archival, or deletion therefore cannot change the captured evidence. Finding and retest relations distinguish original evidence from evidence selected for a particular retest. Identity and lifecycle deletion actions archive or restrict records instead of casually destroying historical context.

Replay credentials and imported request material remain in the local database. Public API serializers and the UI redact authorization, cookie, API-key, URL userinfo, sensitive query/fragment values, and common structured body secret fields by default. Normalized and comparison records are derived from redacted response material.

## Safety defaults

- No outbound request is allowed without an active matching scope rule.
- Only HTTP and HTTPS targets are accepted.
- Redirects are not followed implicitly.
- Request timeout, redirect count, and captured response size are bounded.
- Importing traffic parses and stores it but does not send it.
- HAR, cURL, and OpenAPI inputs are bounded and handled as untrusted data; no
  command execution or external reference fetch is part of import.
- Automated confirmation of vulnerabilities is outside this slice and will remain an explicit operator decision.
- Evidence snapshots and lifecycle history never store replay-capable secret values.
