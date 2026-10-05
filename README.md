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
- run an opt-in, loopback-published deliberately vulnerable demo SaaS with
  deterministic tenant data and authorization defects for local workflow validation.
- validate bounded discovery, HAR/cURL ingestion, replay, identity comparison,
  findings/evidence, and responsive UI behavior against stock OWASP Juice Shop 20.2.0.
- validate classic HTML form discovery, URL-encoded request handling, session
  replay, response comparison, findings/evidence, and responsive UI behavior
  against stock Damn Vulnerable Web Application 2.5.
- validate ordinary registration traffic, compound password redaction,
  session-backed JSON replay, JSON/HTML response comparison, and responsive
  Request Explorer behavior against stock OWASP WebGoat 2026.4.

Reporting/export, credential encryption, and additional external lab
compatibility remain later milestones.

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
make demo-lint demo-test
make frontend-check frontend-test frontend-build
make compatibility-juice-shop
```

## Deliberately vulnerable demo SaaS

The repository includes **Northstar Billing**, an intentionally insecure,
read-only local target for validating Faultweaver without contacting an external
system. It has no outbound client and no persistent data. The host port is bound
to loopback only, the container is read-only with dropped capabilities, and the
service is disabled unless its Compose profile is requested.

```bash
docker compose --profile demo up --build
```

Open the demo directly at `http://127.0.0.1:8088`. From the Compose API, create
scope for `http://demo:8088/` and use that same URL for the baseline assessment.
For host-native backend development, run `python -m demo.app` and scope
`http://127.0.0.1:8088/`.

The public synthetic bearer identities are `demo-alice-token`,
`demo-bob-token`, and `demo-admin-token`. Browser logins are documented on the
demo sign-in page. These values are intentionally public fixtures and must never
be reused outside the demo.

The target contains two explicit authorization defects:

- any authenticated tenant can read another tenant's numbered invoice;
- any authenticated tenant can read the numbered administrator audit endpoint.

It also exposes deterministic passive-baseline signals including missing
defensive headers, a weak demo session cookie, a verbose natural error, an
internal path marker, and a sensitive-looking JSON field name. See
[Demo SaaS](docs/demo-saas.md) for the exact workflow and safety boundary.

## OWASP Juice Shop compatibility

Faultweaver has been validated locally against unmodified OWASP Juice Shop
20.2.0 for bounded baseline discovery, real HAR and cURL ingestion, Request
Explorer and Attack Surface provenance, normal cookie-authenticated replay,
identity-aware comparison, authorization-matrix evidence, findings/evidence,
and responsive browser workflows.

The pinned compatibility service publishes only on `127.0.0.1:3008` and remains
separate from the production Compose services. Run the isolated workflow with:

```bash
make compatibility-juice-shop
```

This is not a claim of full Juice Shop support. The crawler remains deliberately
non-JavaScript, WebSocket HAR records are not imported into the HTTP model, and
the validation does not automate challenges or exploit access-control defects.
See [Juice Shop compatibility](docs/compatibility/juice-shop.md) for the exact
image digest, observed matrix, workflow, and limitations.

## Damn Vulnerable Web Application compatibility

Faultweaver has been validated locally against stock DVWA 2.5 for bounded
anonymous discovery, classic HTML form metadata, real HAR and cURL GET/POST
ingestion, URL-encoded redaction, cookie-authenticated replay, HTML response
comparison, authorization-matrix evidence, findings/evidence, restart
persistence, and responsive browser workflows.

The pinned compatibility service publishes only on `127.0.0.1:4280`; its
database is private to the dedicated Compose network and all resources are
ephemeral. Run the isolated workflow with:

```bash
make compatibility-dvwa
```

This is not a claim of full DVWA support. The crawler does not authenticate or
submit forms, no vulnerability module is exploited, and no artificial Attack
Chain or fixed-state retest is created. See
[DVWA compatibility](docs/compatibility/dvwa.md) for the exact image digests,
observed matrix, workflow, and limitations.

## OWASP WebGoat compatibility

Faultweaver has been validated locally against stock WebGoat 2026.4 for bounded
anonymous discovery, login/registration form metadata, real HAR and cURL
GET/POST ingestion, cookie-backed identities, authenticated JSON replay,
JSON/HTML response comparison, authorization-matrix evidence, Candidate
promotion, findings/evidence, restart persistence, and responsive browser use.

The pinned compatibility service publishes only on `127.0.0.1:4080`; WebWolf
has no published port. Run the isolated, ephemeral workflow with:

```bash
make compatibility-webgoat
```

The validation uses ordinary synthetic registration and lesson-menu traffic.
It does not establish lesson, exploit, or WebWolf coverage. See
[WebGoat compatibility](docs/compatibility/webgoat.md) for the exact image
digest, observed matrix, upstream browser errors, and limitations.

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
