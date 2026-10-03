# Faultweaver

Faultweaver is a local-first Web/API penetration-testing engine and engagement workspace. It is designed around a deliberate workflow: discover and import HTTP traffic, perform conservative analysis, verify candidate findings manually, preserve evidence, connect confirmed issues into attack chains, retest, and report.

Faultweaver is not a promise of complete vulnerability coverage. Automated observations remain candidates until an operator verifies them.

> [!WARNING]
> Use Faultweaver only against systems you own or have explicit authorization to test.

## Current status

Faultweaver is pre-release software. The current vertical slice includes:

- create and reopen engagements;
- authorize exact scheme, hostname, port, and path-prefix scope rules;
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
- persist requests, comparisons, candidates, findings, evidence, retests, Attack Chains, and history in SQLite;
- upgrade fresh or existing pre-migration databases through packaged Alembic migrations.

Reporting/export, crawling and URL baselining, credential encryption, and the deterministic demo target remain later milestones.

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

## Docker Compose

```bash
docker compose up --build
```

The workspace is available at `http://localhost:5173`, the API at `http://localhost:8000`, and SQLite data is retained in the `faultweaver-data` volume.

## First workflow

1. Create an engagement.
2. Add an authorized scope rule. Scope must match before import and immediately before every outbound request or redirect.
3. Open **Import Traffic**, choose Raw HTTP, HAR, cURL, or OpenAPI, and review the
   redacted parse summary before importing.
4. Inspect normalized endpoint provenance and observed/declared state in **Attack Surface**.
5. Select an observed request in **Requests** and choose **Replay** only when you intend to send it.
6. Add at least two identity contexts.
7. Choose **Compare identities** from the original request and save the two replays plus response diff.
8. Inspect observed statuses in **Auth matrix** and review any conservative **Candidates**.
9. Classify the candidate or explicitly promote it, then author the finding prose.
10. Preserve original and retest evidence, move the finding to **Ready for Retest**, and record each verification attempt.
11. Open **Attack Chains**, create a path, add confirmed findings and intermediate steps in an explicit order, attach existing evidence, write the resulting impact, and validate the chain.

A replay or candidate is not a confirmed vulnerability. Promotion is always an explicit operator decision, and automated candidate reasoning is never copied into final finding prose. Attack Chains are also operator-authored: Faultweaver does not infer or auto-generate attack paths.

See [Architecture](docs/architecture.md) for the current boundaries and design decisions.

## Security model

Faultweaver favors conservative request limits and explicit operator actions. It does not implement credential attacks, denial of service, persistence, destructive modification, malware deployment, shell exploitation, or stealth/evasion capabilities.

Identity credentials and imported replay material are stored in the local SQLite database so replay remains possible. API responses, previews, validation errors, logs, and UI views redact common secret-bearing headers, URL credentials and query values, and structured body fields, but the database itself must be protected as sensitive assessment data. Import parsers enforce record and body limits; cURL is parsed only as inert text, and OpenAPI external references are reported but never fetched.

## License

MIT.
