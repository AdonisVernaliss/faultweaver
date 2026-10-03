# Architecture

Faultweaver is a local-first monorepo with two runtime services and one persistent data store.

```text
Browser
  -> SvelteKit workspace and same-origin API proxy
       -> FastAPI application
            -> engagement and scope domains
            -> HTTP parser and traffic repository
            -> scope-gated replay client
            -> SQLite
```

## Backend boundaries

- `engagements` owns engagement metadata and lifecycle state.
- `scope` normalizes and compares scheme, hostname, effective port, and canonical path prefixes.
- `http_traffic` parses imported requests, stores request/response records, renders raw requests, and performs replay.

Every replay URL is checked in the networking layer before a request is sent. Redirects are handled one hop at a time and checked before following. Sensitive authorization and cookie headers are removed if a redirect changes origin. Response capture is bounded to one megabyte by default.

The current pre-release schema is created on startup. A migration system will be added before schema compatibility is promised.

## Frontend boundaries

The SvelteKit application is a client-rendered local workspace. Its server route proxies `/api` to the configured FastAPI service so local and Compose deployments have one browser origin. UI components separate setup dialogs, navigation, and Request Explorer behavior.

## Persistence

SQLite is the source of truth. The default local database is `data/faultweaver.db`; Compose mounts `/data/faultweaver.db` from a named volume. Imported requests and replays are separate records linked through `parent_exchange_id`.

## Safety defaults

- No outbound request is allowed without an active matching scope rule.
- Only HTTP and HTTPS targets are accepted.
- Redirects are not followed implicitly.
- Request timeout, redirect count, and captured response size are bounded.
- Importing a request parses and stores it but does not send it.
- Automated confirmation of vulnerabilities is outside this slice and will remain an explicit operator decision.
