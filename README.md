# Faultweaver

Faultweaver is a local-first Web/API penetration-testing engine and engagement workspace. It is designed around a deliberate workflow: discover and import HTTP traffic, perform conservative analysis, verify candidate findings manually, preserve evidence, connect confirmed issues into attack chains, retest, and report.

Faultweaver is not a promise of complete vulnerability coverage. Automated observations remain candidates until an operator verifies them.

> [!WARNING]
> Use Faultweaver only against systems you own or have explicit authorization to test.

## Current status

Faultweaver is pre-release software. The current vertical slice includes:

- create and reopen engagements;
- authorize exact scheme, hostname, port, and path-prefix scope rules;
- start, monitor, stop, reopen, and compare bounded anonymous baseline assessments
  with stable engagement-scoped `RUN-###` identifiers;
- discover in-scope pages, API-like routes, form metadata, redirects,
  `robots.txt`, and sitemaps without executing JavaScript or submitting forms;
- persist every crawler request in Request Explorer and merge discovered or
  observed routes into Attack Surface with crawler provenance;
- review grouped passive observations and conservative baseline candidates for
  headers, cookies, natural verbose errors, transport, redirects, and banners;
- preview and import raw HTTP, HAR 1.2, cURL, and OpenAPI 3.0/3.1 data without
  executing commands, fetching references, or sending requests;
- retain every observed transaction with stable `IMP-###` batch provenance while
  grouping only exact observed paths or evidenced OpenAPI templates;
- inspect observed and declared endpoints in Attack Surface, and search or
  source-filter stored traffic in the split-pane Request Explorer;
- define engagement-scoped anonymous, bearer, API-key, cookie, and custom-header identities;
- replay a request with explicit auth provenance and per-hop redirect scope checks;
- compare the same request across two identities with normalized text and structured JSON diffs;
- inspect saved evidence in an authorization matrix;
- review conservative authorization-inconsistency candidates with explicit operator classifications;
- promote confirmed candidates into editable findings with stable engagement-scoped `FW-###` IDs;
- capture immutable redacted request, replay, comparison, note, and text evidence as `EV-###`;
- record multiple evidence-backed retests as `RT-###` and surface the latest result;
- track append-only severity, status, promotion, closure, and retest lifecycle events;
- compose confirmed findings and operator-authored intermediate steps into ordered Attack Chains with stable engagement-scoped `AC-###` IDs;
- link existing immutable evidence at chain or step level, validate complete paths explicitly, and preserve archived chains and lifecycle history;
- redact common secrets in API and workspace views while retaining replay material locally;
- persist assessment runs, crawl state, requests, observations, candidates,
  findings, evidence, retests, Attack Chains, and history in SQLite;
- upgrade fresh or existing pre-migration databases through packaged Alembic migrations.

Reporting/export, credential encryption, and the deliberately vulnerable demo
target remain later milestones.

## Architecture

- FastAPI, SQLAlchemy, and SQLite backend
- SvelteKit and TypeScript frontend
- Docker Compose for local deployment

The backend validates scheme, hostname, port, and path restrictions before outbound traffic is sent. Redirect destinations are evaluated independently.

### Import model and known limitations

- **Raw HTTP** accepts one request line, headers, and optional body relative to a
  supplied base URL.
- **HAR 1.2** imports request/response transactions, duplicate headers, cookies,
  timings, redirects, and textual or valid UTF-8 base64 bodies. Malformed entries
  are reported individually; binary bodies are represented as omitted rather
  than copied into operator-safe views.
- **cURL** supports the common browser-copy subset: URL, method, headers,
  cookies, `--data`, `--data-raw`, `--data-binary`, `--json`, `--get`, quoting,
  and multiline input. It is parsed as data and never executed; file reads,
  shell expansion, and execution/network-control options are rejected or warned.
- **OpenAPI 3.0/3.1** accepts JSON or safe YAML and records operations,
  parameters, request/response content types, operation IDs, tags, and security
  schemes. Internal references are resolved where supported. External references
  remain unresolved warnings and are never fetched; declared servers are not
  contacted and schemas do not generate requests.

Observed HAR, cURL, and Raw HTTP transactions remain concrete Request Explorer
records. OpenAPI contributes declared operations. Attack Surface keeps these
states distinct and uses a declared template only when the same method and origin
provide evidence for matching an observed path. Default limits are 10 MB per
document, 5,000 records, and 1 MB per captured request or response body.

## Development

Prerequisites: Python 3.13+, `uv`, and Node.js 22.17+.

```bash
uv sync --project backend --all-groups
npm ci --prefix frontend
```

Run the API and frontend in separate terminals:

```bash
uv run --project backend uvicorn faultweaver.app:app --reload
npm run dev --prefix frontend
```

Open `http://localhost:5173`. The frontend proxies `/api` to `http://localhost:8000` by default. Local state is stored in `data/faultweaver.db`.

Run the validated checks:

```bash
make backend-lint backend-test
make frontend-check frontend-test frontend-build
```

## Baseline assessment safety model

**New Baseline** accepts one exact authorized HTTP or HTTPS URL. Before the
initial request, every discovered URL, and every redirect follow-up, the same
scheme/hostname/effective-port/path-prefix scope matcher used by replay runs in
the networking boundary. Out-of-scope links and redirects are recorded as
skipped provenance and are never requested.

Defaults are intentionally conservative: 50 pages, depth 3, 75 total requests,
1 request/second, concurrency 2, a 10 second timeout, 1 MB response capture,
and 3 query variants per path. Operators can tighten or raise these bounded
limits in the start dialog. Automatic requests are anonymous `GET` only. Forms
are metadata, resources are not downloaded automatically, JavaScript is not
executed, and `robots.txt` is discovery information rather than authorization.
Passive checks cover contextual defensive headers, cookie attributes, banners
and stack traces, redirects, forms, mixed-content references, cache policy,
internal path patterns, and sensitive-looking JSON field names. Low-confidence
or application-specific signals remain informational instead of becoming
candidates.

The run detail preserves partial work after Stop or a request failure. A process
restart recovers stale Pending/Running runs as Stopped instead of resuming
uncontrolled work. Passive observations remain separate from candidates;
candidate-level signals are deduplicated and require manual verification before
promotion. See [Baseline assessments](docs/baseline-assessments.md) for checks,
limits, and known constraints.

## Docker Compose

```bash
docker compose up --build
```

The workspace is available at `http://localhost:5173`, the API at `http://localhost:8000`, and SQLite data is retained in the `faultweaver-data` volume.

## First workflow

1. Create an engagement.
2. Add an authorized scope rule. Scope must match before import and immediately before every outbound request or redirect.
3. Open **Assessments**, choose **New Baseline**, review the request/depth/rate
   limits, and start the exact in-scope target.
4. Monitor concrete request/page/queue counters, stop gracefully when needed,
   and review Discovered Surface, Requests, Observations, Candidates, Warnings,
   and Configuration in the persisted run.
5. Open **Import Traffic**, choose Raw HTTP, HAR, cURL, or OpenAPI, and review the
   redacted parse summary before importing.
6. Inspect normalized endpoint provenance in **Attack Surface**.
7. Select an observed request in **Requests** and choose **Replay** only when you intend to send it.
8. Add at least two identity contexts and use **Compare identities** when relevant.
9. Inspect the **Auth matrix** and review any conservative **Candidates**.
10. Classify a candidate or explicitly promote it, then author the finding prose.
11. Preserve original and retest evidence, move the finding to **Ready for Retest**, and record each verification attempt.
12. Open **Attack Chains**, create a path, add confirmed findings and intermediate steps in an explicit order, attach existing evidence, write the resulting impact, and validate the chain.

A replay or candidate is not a confirmed vulnerability. Promotion is always an explicit operator decision, and automated candidate reasoning is never copied into final finding prose. Attack Chains are also operator-authored: Faultweaver does not infer or auto-generate attack paths.

See [Architecture](docs/architecture.md) for the current boundaries and design decisions.

## Security model

Faultweaver favors conservative request limits and explicit operator actions. It does not implement credential attacks, denial of service, persistence, destructive modification, malware deployment, shell exploitation, or stealth/evasion capabilities.

Identity credentials and imported replay material are stored in the local SQLite database so replay remains possible. API responses, previews, validation errors, logs, and UI views redact common secret-bearing headers, URL credentials and query values, and structured body fields, but the database itself must be protected as sensitive assessment data. Import parsers enforce record and body limits; cURL is parsed only as inert text, and OpenAPI external references are reported but never fetched.

## License

MIT.
