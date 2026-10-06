# OWASP Mutillidae II compatibility

Faultweaver was validated locally against the unmodified official OWASP
Mutillidae II container distribution for the bounded workflows below. This
completes the four-lab compatibility milestone; it is not a claim of universal
application support or comprehensive vulnerability coverage.

## Validated distribution

| Component | Official image tag | Pinned digest |
| --- | --- | --- |
| Web application | `webpwnized/mutillidae:www-2.12.7` | `sha256:71c1e63420311da0d4561a2592afdb1a12ac28c58d2307d3c0aa7844f9b30441` |
| Database | `webpwnized/mutillidae:database-2.12.7` | `sha256:bd79b51b9a29eb852b2f85bed2629407df6355d7f729b66913e0abe1b7a99ed6` |

- Validation date: 2026-10-05.
- The web image **reports application version 2.12.8**, despite its 2.12.7 tag.
  The integration test verifies the observed version. Tag and application
  version are not interchangeable for this distribution.
- These pinned images are `linux/amd64`; this run used platform emulation on
  an arm64 host. Native arm64 image compatibility was not established.
- Only `127.0.0.1:4380:80` is published. The database has no host port and lives
  on the dedicated Compose network with an ephemeral named volume.
- LDAP, database-admin UI, and other upstream optional services are not run.
  No target source or image was patched; these are test-only dependencies.

Upstream references: [OWASP project](https://owasp.org/projects/mutillidae-ii),
[official Docker distribution](https://github.com/webpwnized/mutillidae-dockerhub),
[upstream Compose example](https://github.com/webpwnized/mutillidae-dockerhub/blob/main/docker-compose.yml),
and [image repository](https://hub.docker.com/r/webpwnized/mutillidae).

## Reproducible validation

Run separately from the normal unit/integration suite and CI:

```bash
make compatibility-mutillidae
```

The runner starts its dedicated project, waits for both services, tests the
workflow, and removes its containers, network, and database volume on exit.
It refuses to reuse an already-running compatibility project. A stopped
project from a previous run is removed before starting. On a fresh database,
the test uses the application's ordinary setup page before registration.
`FAULTWEAVER_MUTILLIDAE_PORT` changes the host port, not the loopback binding.
The test rejects non-HTTP, non-loopback, credential-bearing, or non-root target
origins. No external application is contacted by the workflow.

Synthetic credentials are generated in memory. Faultweaver uses a temporary
SQLite database, which retains sensitive replay material until removed.
No raw HAR, live session cookie, password, database, or screenshot is tracked.
The independent Chrome capture and responsive walkthrough described below are
manual validation, not part of this runner or ordinary CI.

## Compatibility matrix

| Capability | Result | Observed validation |
| --- | --- | --- |
| Baseline crawler | Partially validated | Three anonymous runs with at most six requests each, four pages, depth zero or one, concurrency one, and two query variants per path. Authenticated crawling and complete application enumeration are not covered. |
| HTML link discovery | Validated | Query-routed links, nested paths, robots.txt, and a natural missing sitemap were represented; canonical discovery records were unique and scope/depth/query limits produced explicit skip reasons. |
| Form discovery | Partially validated | Login, registration, and document-viewer metadata persisted through baseline runs. Additional authenticated HTML was passed through the same discovery parser. GET/POST, hidden, text, password, textarea, radio, select, file, and multipart metadata were observed; checkbox controls were not observed in this sample. No discovered form was automatically submitted. |
| GET parameters | Validated | Repeated names, percent encoding, literal plus, spaces, and empty values survived real HAR/cURL import; query variation bounds prevented unbounded enumeration. |
| POST forms | Validated | Ordinary synthetic registration and login were captured; explicit login replay used the same synthetic user's credentials. |
| URL-encoded bodies | Validated | Ordered repeated and empty fields remained parseable; password values were redacted without changing non-secret values. |
| Multipart representation | Partially validated | A normal empty file-control submission returned "No file was uploaded". HAR and cURL `--data-binary` preserved its textual envelope and boundary. No file content was supplied, stored, or replayed; binary upload semantics were not tested. |
| HAR import | Validated | Automated 13/13 real HTTP request/response pairs and independent Chrome 241/241 local records imported with zero skips in the final batches. Binary response omissions are explicit, not silent successful payload capture. |
| cURL GET | Validated | A cookie-bearing query request previewed and imported without executing the command. |
| cURL POST | Validated | Login `--data-raw` and empty multipart `--data-binary` bodies imported. No file-read or `-F` support was added. |
| Cookies/session state | Validated | A generated synthetic user's PHPSESSID was placed in a separate Identity and used for ordinary session-aware replay; operator-safe views redacted it. |
| Request Explorer | Validated | Methods, query strings, request/response bodies, redirects, statuses, import provenance, and separate replay records remained inspectable. Search reached records beyond the first 100 and Load more displayed 200 rows. |
| Attack Surface | Partially validated | GET and POST `/index.php` remain two method/path groups with crawler/HAR/cURL provenance. Query-dispatched pages are not invented path templates. A generalized observed-parameter inventory is not provided by the current model. |
| Replay | Validated | GET and URL-encoded login POST replayed with the selected Identity. The login 302 was followed to HTML/200; source requests remained immutable. An out-of-scope replay was rejected. |
| Response normalization | Validated | Identical HTML matched exactly, repeated naturally changing HTML remained highly similar, and a real HTML/404 response remained different in status, size, and normalized content. No target-specific volatile-field rules were added. |
| Identity response comparison | Validated | Authenticated upload-form GET versus an anonymous login redirect both ended at HTML/200 but differed in redirect chain, length, and normalized body. Chrome showed about 92% similarity, not equivalent access. |
| Authorization matrix | Validated | Synthetic Identity and Anonymous cells retained their observed 200 statuses and replay links. Equal status alone did not imply equal representations or an authorization flaw. |
| Baseline observations | Validated | Repeated header/banner signals were grouped within each run with occurrence counts; six observation groups and two conservative candidates were observed per run. Separate runs retain separate observations. |
| Candidate workflow | Validated | Normal session-gated comparison produced no automatic authorization Candidate. A passive missing-CSP Candidate was reviewed, accepted, and explicitly promoted. |
| Finding | Validated | Low-severity FW-001 records the observed missing CSP header with operator-authored scope, impact, reproduction, and remediation. It is not an exploit claim. |
| Evidence | Validated | EV-001 preserves the source HTTP response, and EV-002 preserves a response comparison. Redacted snapshots remain immutable after reopening the API. |
| Redaction | Validated | Generated password/session values were absent from tested public API payloads, captured logs, preview/detail/comparison/evidence views, and browser DOM. This does not encrypt the backing database. |
| Restart persistence | Validated | A new API instance reopened the same SQLite file and recovered imports, completed run, comparison, finding, and unchanged evidence. |
| Responsive browser behavior | Validated | Assessment/forms, Requests, Attack Surface, Authorization Matrix, Findings, Evidence, and Comparison were checked at four widths: 28 view/viewport combinations, zero document horizontal overflow. |
| Retest | Not applicable | No target fix or fixed-state response was manufactured. The normal regression suite covers the subsystem separately. |
| Attack Chains | Not exercised | One passive finding provides no meaningful multi-finding chain. No chain was fabricated. |
| OpenAPI import | Not exercised | No application contract was supplied or inferred in this workflow. |
| Exploits and vulnerability exercises | Not exercised | Validation used ordinary synthetic application traffic, empty file controls, and passive observations only. |

## Traffic and workflow

1. Initialize the fresh owned lab, then register and log in a synthetic user
   through ordinary forms. Capture the login redirect and landing response.
2. Read login, document-viewer, text-file-viewer, and upload-form pages. Inspect
   their form metadata without submitting document paths or file content.
3. Submit the normal upload form with its file control empty, request the
   connectivity JSON endpoint, and request one deliberately missing local URL.
4. Run three bounded anonymous baselines, import the 13 captured transactions
   as `IMP-001`, and import three inert cURL representations as `IMP-002` through
   `IMP-004`. cURL imports have no response until explicitly replayed.
5. Inspect Requests and Attack Surface, replay the ordinary GET/login POST,
   compare a session-gated GET, inspect the matrix, and preserve passive finding
   and comparison evidence. Reopen the API against the same database.
6. Independently capture normal Chrome activity, import its local HAR, and
   inspect the real Faultweaver UI at desktop, tablet, and mobile widths.

The representative baseline used 5 requests and visited 3 pages; the other
two used 1 request each. Its 209 discovery records comprised 5 requested, 82
out-of-scope, 118 query-limited, and 4 depth-limited URLs. These are discovery
records, not 209 network transactions. The first run recorded three forms;
the other two recorded two each (seven persisted form records across runs).
The test asserts no crawler request contains a `do=` action or setup path.

The automated HAR contains **13 entries and 13 response-bearing HTTP
transactions**, all accepted. These cover GET, URL-encoded POST, empty
multipart POST, HTML/200, login/302, JSON/200, and HTML/404. The body tests
include repeated `note` fields, empty values, and encoded `&`, `+`, and `%`.
The normalizer also makes a repeated page request outside the HAR sample;
baseline and replay requests are additional traffic, not part of that count.

The independent Chrome HAR final batch `IMP-006` contains **241 local entries,
241 imported HTTP transactions/responses, and zero skips**. There are **104
explicit binary response-body omission warnings**: those response records
exist, but their binary payloads are not claimed to be retained.

An earlier pilot `IMP-005` correctly accepted only 10 of 241 entries and skipped
231 outside the initial narrow path scopes. Exact captured local resource
paths were then authorized for browser import only; the baseline was not rerun
under wider scope. The successful capture was imported as a new batch, not
silently substituted for the pilot. Production scope enforcement was unchanged.

## Browser results and generic production fix

The browser blocked **27 external resource requests before transmission** and
excluded those blocked entries from the import. Mutillidae produced 28 console
resource errors: the 27 intentional blocks plus a local 404 for
`/documentation/robots.php`. There were no target page-script errors in this
sample. These target issues did not prevent normal capture or form navigation.

Faultweaver produced zero console errors, page errors, failed requests, or HTTP
error responses during the final walkthrough. The four viewports were
1440x1000, 1024x900, 768x900, and 375x812. Assessment's discovered-surface tab
included form method/action/encoding/count metadata; individual field metadata
was checked through the API/parser, not claimed as a dedicated field UI.
Screenshots were inspected locally; raw captures and screenshots are not
published or committed.

This realistic capture exposed a generic Request Explorer defect: local
filtering searched only the first 100 loaded records. The fix:

- queries all engagement records on the server by method, URL/query, or status;
- treats `%` and `_` as literal search text rather than SQL wildcards;
- combines the query with the existing source filter and stable pagination;
- adds bounded Load more behavior, full and filtered totals, and stale-result
  protection when filters or engagements change;
- avoids duplicate displayed rows if new captures shift an offset page.

Backend and frontend regressions cover older matches, pagination, query
encoding, source/engagement isolation, stale responses, and duplicate merges.
No Mutillidae-specific production logic, dependency, redaction exception,
crawler relaxation, or Candidate heuristic change was introduced.

## Regression validation

| Check | Result |
| --- | --- |
| Locked installation | `uv sync --project backend --all-groups --locked` and `npm ci --prefix frontend` passed without manifest or lockfile changes. |
| Backend | 80 tests passed, including migration coverage. |
| Demo | 5 tests passed; combined backend/demo run: 85 passed. |
| Juice Shop compatibility | 1 workflow passed. |
| DVWA compatibility | 1 workflow passed. |
| WebGoat compatibility | 1 workflow passed. |
| Mutillidae compatibility | 1 workflow passed in 59.46 seconds, including restart persistence. |
| Frontend | 18 tests across 8 files passed. |
| Ruff | Lint passed; 107 Python files passed format checks across backend, demo, and compatibility. |
| Types | Svelte check: zero errors and zero warnings. |
| Build | Frontend production build and API/web/demo Docker builds passed. |
| npm audit | Zero vulnerabilities. |
| Chromium | 28 view/viewport combinations, zero document overflow, and no Faultweaver console/page/network errors. |
| Cleanup | All four runners removed their temporary target containers/networks/volumes; inspection found none remaining. |

Existing Starlette/SQLite deprecation warnings remain. Host Node 25 is outside
Vitest's declared engine range; tests passed and the Docker frontend build
uses Node 22. Browser-resource failures from the target are listed separately
above and are not hidden in the Faultweaver error count.

## Remaining limitations

- The baseline is anonymous, GET-only, non-JavaScript, and deliberately narrow.
  Scope is path-based, not a per-query authorization language. Applications
  can have state-changing GET links; the exercised seed/order/query bounds
  avoid this lab's toggle/setup links. This does not prove every URL on a
  broadly scoped application is side-effect-free.
- Form values are not discovery metadata. Authenticated form pages were also
  tested directly through the parser, not discovered by an authenticated crawl.
- Multipart coverage is an empty textual envelope, not file transport. Binary
  HAR response bodies remain omitted with warnings.
- Query-routed pages share `/index.php` in Attack Surface; observed parameter
  cataloging and checkbox discovery coverage remain incomplete here.
- Large similar HTML comparison was slow: the final browser comparison took
  about 25.5 seconds for roughly 56–59 KB bodies. Normalization and conservative
  similarity rules were not weakened to improve this result. This is a historical
  measurement; the exact-comparison optimization and current measurements are
  recorded in [Reporting release validation](../release-validation.md#performance).
- Offset pagination is not a snapshot of a continuously changing capture set;
  duplicate rows are suppressed, but operators should refresh after traffic
  changes when they need a current complete view.
- Session expiry requires an ordinary new synthetic login/Identity. The final
  browser comparison used a fresh session, not an expired test cookie.
- The workflow was rerun with authenticated encrypted storage during
  [Secret-Storage Hardening](../secret-storage.md#validation-results): **Validated**.
  The original coverage limits remain unchanged. Raw external captures and any
  legacy plaintext backups still require separate protection. The repeat took
  60.56 seconds; the HTML comparator alone took 25.701 seconds, consistent with
  the existing approximately 25-second limitation. This is not a controlled
  before/after comparison of identical target responses.
- Reporting release-polish regression: **Validated**, existing workflow passed
  in 4.23 seconds. Similar HTML (48,020/51,259 normalized characters) compared in
  0.206 seconds with score 0.9185 unchanged from the pre-change profile. No new
  Mutillidae behavior, exploit coverage or target-specific production logic was added.
- Results apply only to the pinned distribution and documented workflows.
  Retest, chains, exploits, and omitted form/file behaviors must not be inferred
  from a green compatibility workflow.
