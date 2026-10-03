# Architecture

Faultweaver is a local-first monorepo with two runtime services and one persistent data store.

```text
Browser
  -> SvelteKit workspace and same-origin API proxy
       -> FastAPI application
            -> engagement and scope domains
            -> engagement-scoped identity contexts
            -> HTTP parser and traffic repository
            -> scope-gated replay client
            -> response normalization, structured diff, and candidate analysis
            -> finding, immutable evidence, operator note, and retest lifecycle
            -> SQLite
```

## Backend boundaries

- `engagements` owns engagement metadata and lifecycle state.
- `scope` normalizes and compares scheme, hostname, effective port, and canonical path prefixes.
- `http_traffic` parses imported requests, stores request/response records, renders raw requests, and performs replay.
- `identities` owns local authentication contexts and applies them only within their engagement.
- `analysis` normalizes bounded responses, stores explainable comparisons, derives the authorization matrix, and emits conservative candidates.
- `findings` owns explicit candidate promotion, stable display IDs, report prose, immutable evidence snapshots, operator notes, retest attempts, and append-only lifecycle events.

Every replay URL is checked in the networking layer before a request is sent. Redirects are handled one hop at a time and checked before following. Sensitive authorization and cookie headers are removed if a redirect changes origin. Response capture is bounded to one megabyte by default.

Packaged Alembic migrations run on startup. The baseline revision can adopt the original pre-migration schema after validating every expected table and column; revisions `0002` and `0003` evolve identity/analysis and finding-lifecycle data without dropping stored engagements or traffic.

## Frontend boundaries

The SvelteKit application is a client-rendered local workspace. Its server route proxies `/api` to the configured FastAPI service so local and Compose deployments have one browser origin. The candidate review, finding report, evidence library, and retest ledger are distinct views but keep promotion and verification in one continuous workflow.

## Persistence

SQLite is the source of truth. The default local database is `data/faultweaver.db`; Compose mounts `/data/faultweaver.db` from a named volume. Imported requests and replays are separate records linked through `parent_exchange_id`. Comparisons link an immutable original to both replay records and their identity contexts; candidates remain linked after promotion. Per-engagement counters allocate stable `FW-###`, `EV-###`, and `RT-###` display IDs.

Evidence stores a redacted point-in-time JSON snapshot rather than a live rendering of its source. Source edits, archival, or deletion therefore cannot change the captured evidence. Finding and retest relations distinguish original evidence from evidence selected for a particular retest. Identity and lifecycle deletion actions archive or restrict records instead of casually destroying historical context.

Replay credentials remain in the local database. Public API serializers and the UI redact authorization, cookie, API-key, and common structured body secret fields by default. Normalized and comparison records are derived from redacted response material.

## Safety defaults

- No outbound request is allowed without an active matching scope rule.
- Only HTTP and HTTPS targets are accepted.
- Redirects are not followed implicitly.
- Request timeout, redirect count, and captured response size are bounded.
- Importing a request parses and stores it but does not send it.
- Automated confirmation of vulnerabilities is outside this slice and will remain an explicit operator decision.
- Evidence snapshots and lifecycle history never store replay-capable secret values.
