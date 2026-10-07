# Full product and security release audit

Local release-gate review, 2026-10-07. **READY WITH DOCUMENTED LIMITATIONS** for
a separately authorized public release-candidate publication. This is a local
development audit, not independent third-party assurance or complete vulnerability
coverage. No repository, tag, release or deployment was published.

Baseline: clean `main`, `4272b159f578a254f0537c153ccdcabfa43a20e2`, 61 commits.
Tested code: `37be1428b1aadd9309a58920c7732dade59050ac`, 71 commits; the following
documentation commit records this gate. Migration head remains `0008`, application
version `0.1.0`, changelog Unreleased. No schema migration, dependency-version
update, history rewrite or new scanner was introduced.

## Release-relevant corrections

| Commit | Correction and release relevance |
| --- | --- |
| `27556ce` | Reject ambiguous scope URLs; strip credentials and cookie-jar state at cross-origin redirects; disable ambient proxy/netrc configuration. Prevent unintended outbound authentication or destinations. |
| `9fc9937` | Redact every Identity custom-header value, preserve immutable sensitivity in encrypted request-header JSON, protect credential reflections and sanitize validation/transport errors. Stored replay material remains unchanged. |
| `f1491f2` | Bound expanded OpenAPI aliases, nesting, references and server-expanded endpoints; reject non-JSON YAML structures safely; tolerate malformed HAR URL/timing metadata. |
| `f416c99` | Validate optional Evidence source ownership even for notes; reject ambiguous CORS origins; add no-store/nosniff/no-referrer to direct API responses. |
| `621c271` | Reject late Assessment selections and Engagement refresh/action results so older responses cannot overwrite the current workspace. Reproduced in the production browser. |
| `3529bb0` | Allowlist Docker inputs, exclude private files generically, identify Python 3.13 and Node 22 development runtimes. No dependency versions changed. |
| `a75749f` | Keep baseline requests cookie-free, capture actual replay headers including same-origin redirect cookies, bound discovery metadata, remove raw transport exception text. |
| `034c11c` | Handle unencodable replay/compare headers through safe errors instead of unhandled exceptions. |
| `16a2dba` | Permit manual Candidate selection after Assessment navigation. Reproduced and retested in Chromium. |
| `37be142` | Protect older comparison payloads, immutable comparison snapshots and credential-bearing redirect paths at read/export boundaries without rewriting sources. Update DVWA assertions for stricter redaction while checking raw replay data is preserved. |

Final whole-change review covered the corrections with their callers, storage
boundaries, UI transitions and regression coverage. No unrelated refactoring or
target-specific production logic was introduced.

## Security and correctness matrix

Statuses describe exercised boundaries, not universal security guarantees.

| Capability | Status | Evidence and boundary |
| --- | --- | --- |
| Engagement/domain ownership | Validated | Scoped Identity, Candidate, Finding, Evidence, chain/step, Retest and Report relationships; foreign/missing references and corrupt report links rejected. Optional Evidence sources now checked for all types. Global request/comparison IDs belong to the single trusted operator, not a multi-user authorization boundary. |
| URL scope | Validated | Exact scheme/host/effective port/path; inactive rules, dot segments, encoded paths, controls, userinfo, deceptive hosts and redirects covered. Import/discovery never grants scope. |
| Outbound requests | Validated | Per-hop scope, explicit redirect/time/body bounds, verified TLS defaults, no ambient proxy/netrc credentials. Known and Identity-managed credentials do not cross origins, including port changes. |
| DNS/network egress isolation | Partially validated | Scope is a URL allowlist, not a resolved-IP firewall. Local/private targets are legitimate supported targets. DNS pinning/rebinding resistance is not provided or claimed; operators must control the authorized destination and environment. |
| HAR/raw HTTP/cURL | Validated | Inert parsers; size/count/body limits, malformed entries, duplicate headers, textual/base64/binary representation, cookies and batch provenance. cURL is never executed; filesystem/shell/execution options are unsupported. |
| OpenAPI | Validated | Safe YAML/JSON, no external-reference/server fetching, cycle/depth/expanded-size/endpoint bounds and numeric YAML response codes. Unsupported constructs remain warnings, not generated traffic. |
| Anonymous bounded crawler | Validated | GET only; no forms/JavaScript; request/page/depth/rate/concurrency/timeout/body/query limits, stop/restart, deduplication and scope skips. Response cookies are not sent by later baseline requests. |
| Discovery metadata | Validated | At most `min(10000, max_requests * 20)` unique stored discoveries per run, including skipped links; warning when further links are omitted. Small mock fixture reproduced the missing cap. |
| Identity/replay provenance | Validated | Original/explicit Identity and anonymous semantics, archive/foreign-ID handling, actual final-hop headers and persistent sensitivity metadata. No credential guessing or session acquisition. |
| Comparison/Candidates | Validated | Exact matcher regression corpus, normalization/diff/status/redirect semantics, matrix untested cells, conservative rejection and manual promotion. Thresholds unchanged. Baseline grouping is per run/check/host; differential Candidates retain per-comparison provenance, not global deduplication. |
| API/UI/Evidence redaction | Validated | Custom credentials, common secret fields, known reflections, edited/archived Identity provenance, legacy comparisons/snapshots and safe errors. Five distinct generated markers absent from exercised API/Evidence/report outputs. Reads do not rewrite raw sources or immutable snapshots. |
| General secret/PII classification | Partially validated | Arbitrary prose, paths, response data and prior exports can remain confidential. Known-value redaction can also hide non-secret text equal to a credential. Review every deliverable. |
| SQLCipher/key boundary | Validated | Cipher format 4, encrypted tables/indexes, independent explicit key, wrong/missing keys and tampering fail closed. No plaintext fallback, automatic key creation or silent replacement. No custom cipher. |
| Filesystem/key permissions | Validated | Regular private files, symlink/ownership/mode/separation guards and offline migration boundaries. Live DB mode `0600`, API UID/GID `65534`; key separately mounted and read before privilege drop. |
| Logs/images/database scans | Validated | Generated markers/key encodings absent from exercised logs, encrypted database/available sidecars and built API/web/demo image streams. Unit tests additionally cover WAL/journal/crash/deleted-page cases; absent live sidecars are not claimed as live measurements. |
| Report injection/export paths | Validated | Escaped text, restrictive CSP/sandbox, malicious prose/target text, Markdown fence breaks, data-only JSON, safe REP/revision filenames and no arbitrary server export destination. No remote assets. |
| Headers/CORS | Validated | Workspace CSP/no-store; direct API no-store/nosniff/no-referrer; origins reject wildcard/control/path/credential/query/fragment/port-zero forms. Not a substitute for authentication. |
| Local demo/lab isolation | Validated | Optional owned Compose projects, loopback published ports, bounded existing runners and synthetic credentials. Unrelated resources untouched; ordinary tests launch no labs. |

## Persistence and recovery

**Validated:** fresh encrypted initialization; historical Alembic upgrade fixtures
through `0008`; encrypted `0007` to `0008`; explicit plaintext conversion with
independent backup, typed-row/schema checks and failure recovery; wrong/missing
keys; authenticated-page tampering; copied-database recovery with the correct
key; restart and interrupted-run handling. Storage tests cover failed migration,
replace/verification and crash-left WAL recovery.

A disposable Compose DB rejected missing/wrong keys with unchanged database
SHA-256, then reopened with the correct key. API recreation preserved **25
endpoint/export digests** spanning traffic, Identities, analysis, Findings,
Evidence, chains, Retests, two Reports and all three formats. A separate fresh
source-only installation passed `make down` / `make up` with the same 25 digests
unchanged.

File-provider operation was exercised live. macOS native-store operation has
historical milestone evidence but was **Not exercised** again; Linux/Windows
native stores are **Not exercised** live. Fail-closed provider logic is unit-tested.
Key loss is unrecoverable; rotation, rollback defense, host compromise protection
and reliable Python memory zeroization are not claims. See [storage](secret-storage.md).

## Reporting and browser validation

Northstar traversed bounded discovery, Identity replay/comparison, manual
promotion, four Findings, immutable Evidence, a validated three-step chain,
Still Vulnerable Retest, Report and HTML/Markdown/JSON export. UI checks covered
editing, inclusion/exclusion, Ready, generation, three downloads, archive/restore,
unsaved navigation and unchanged old revisions after draft edits. Schema `1.0`,
inclusion counts and canonical content agree across renderers. Reports use
immutable Evidence, not mutable HTTP/Identity payloads. Already-exported documents
cannot be retroactively redacted.

Production Chromium passed **88 populated-view checks** at **1440×1000,
1024×900, 768×900 and 375×812**, repeated on the clean installation. Coverage:
Engagement context, Assessments, imports, Attack Surface, Requests/detail,
read-only replay/comparison, Identities, matrix, Candidates, Findings, Evidence,
chains, Retests, Report sections and preview. No unexpected console/CSP errors,
failed HTTP responses, visible fixture credentials or page/preview overflow.
Contained table scrolling is intentional. Ten empty views, delayed Engagement
loading/switching, late Assessment responses, Candidate navigation and controlled
503 Report error/reload recovery were separately checked. The intentional 503 is
not an unexpected failure. Dialog Tab/Shift+Tab, Escape and focus return passed.
This is **Chromium-only**, not accessibility certification.

Offline HTML rendered from disk with the **API stopped and HTTP requests blocked**,
without external assets. Print media hid navigation and wrapped text without
horizontal overflow. Physical printer/PDF pagination and third-party Markdown
viewers are **Not exercised**. A native PDF exporter is **Not applicable**.

## Bounded performance

Local timings, not service-level guarantees. Traced and untraced measurements
are not directly comparable.

| Workload | Measured result |
| --- | --- |
| Similar HTML, 51,516/51,550 characters | Five-run median **48.97 ms**, unchanged exact ratio **0.9995536840471154**; separate traced peak **19,936,676 bytes**. |
| Repetitive shifted 10,000-character text | Five-run median **6.19 ms**, ratio **0.9999**. Unit corpus includes 3,969 exhaustive binary pairs and 1,000 seeded Unicode/range cases. |
| HAR: 1,000 records / 1,542,988 bytes | **1,796.88 ms**, no outbound import traffic. |
| Request list / search among 1,000 records | Ten-call medians **13.60 / 38.83 ms**; bounded 100-item page, real `q` search one match. Five 200-item pages were stable and covered 1,000 distinct IDs. |
| Oldest request detail | **5.50 ms**, correct selected ID. |
| Four-Finding Northstar report, clean installation | **23.30 ms**, with chain, Retest and Evidence. |
| 50 Findings / 100 Evidence, 5.28 MB source text | **1,251.66 ms with memory tracing**, peak **1,891,436 bytes**; canonical JSON **402,384 bytes**, HTML **396,922 bytes**. Evidence lists omitted snapshots; bounded excerpts rendered through the final record at desktop/mobile widths without overflow or network requests. |

The larger report fixture initially lacked scope and correctly received 422;
adding its explicit synthetic scope completed the check without changing the
product. General/adversarial large-data scaling remains **Partially validated**;
no enterprise-load, universal latency or worst-case memory guarantee is made.

## Clean-room rehearsal and final tests

A local clone of tracked Git source used a **new venv, new npm install, new
independently stored key and new empty Compose volume**. No ignored source, prior
DB, developer key, capture or private configuration was needed for startup.
External test drivers supplied synthetic interactions after startup; they are not
application dependencies.

README Quick Start succeeded: locked `uv` install, explicit `init-key`, `make up`,
first Engagement through `http://localhost:5173`, optional `make demo-up`, full
workflow/report and documented restart. `make help` and `make install validate`
were exercised. Node 22 was selected through a disposable Docker npm runner
because host Node 25 is outside the validated range; source and make targets
were unchanged. This selects a supported runtime, not private application setup.

| Final check | Result |
| --- | --- |
| Backend | **176 passed**, 24.42 s; migrations/storage, ownership, imports/scope, comparisons and **18 Report cases** included. |
| Demo | **5 passed**, 4.02 s; full lifecycle and persisted exports. |
| Frontend | **31 passed in 11 files** under Node 22. |
| Python lint/format | **137 files** across backend/demo/compatibility; clean diff whitespace. |
| Svelte/TypeScript | **0 errors, 0 warnings**. |
| Locked installs/builds | Fresh `uv sync --locked` and `npm ci`; production frontend and API/web/demo Docker builds passed. |
| Remote CI | **Not exercised** before publication. Inspected read-only workflow uses Python 3.13/Node 22, locked installs/tests/builds, no lab traffic or private secrets. |

Existing Starlette/httpx TestClient and historical SQLite datetime-adapter
deprecations were recorded, not suppressed. Validated runtimes: local Python
**3.13.5**, container Python **3.13.11**, Node **22.23.3**, uv **0.11.8**, Docker
**29.4.2**, Compose **5.5.1**, container SQLCipher **4.12.0 community**, cipher format **4**.

## Compatibility matrix

Final existing runners passed after the last code correction. These are
compatibility regressions, not new exploitation or complete lesson coverage.
Original per-capability limitations remain authoritative.

| Target | Status | Final pytest / total runner time | Detailed limits |
| --- | --- | --- | --- |
| Juice Shop **20.2.0** | Validated | **1 passed, 1.95 s / 9.001 s** | [Matrix](compatibility/juice-shop.md) |
| DVWA **2.5** | Validated | **1 passed, 1.98 s / 15.736 s** | [Matrix](compatibility/dvwa.md) |
| WebGoat **2026.4** | Validated | **1 passed, 2.48 s / 14.934 s** | [Matrix](compatibility/webgoat.md) |
| Mutillidae II **2.12.8** | Validated | **1 passed, 4.15 s / 18.076 s** | [Matrix](compatibility/mutillidae.md) |
| Northstar full Finding/Evidence/chain/Retest/Report lifecycle | Validated | Unit/demo, live API, production UI, clean-room and restart | Synthetic local fixtures only. |
| New exploit/lesson coverage; live Report authoring against each external lab | Not exercised | No expansion inferred from successful runners | Report UI validated with Northstar. |

## Dependencies, licensing and source hygiene

At check time, npm audit reported **0 vulnerabilities** and pip-audit **0 known
advisories** for **48 registry-pinned Python packages** across lockfile platform
variants (also zero in the 41-package active-platform export). Advisory absence
is not proof of safety; OS/base-image packages and unpublished issues are outside
this package-advisory result. No dependency versions changed.

Project MIT and direct dependency licenses were reviewed: Python MIT/BSD-3-Clause
plus sqlcipher3's bundled Zlib-style notice; frontend MIT except TypeScript
Apache-2.0. Existing notices retained; no new third-party code/artwork copied.
This is not a complete transitive SBOM, container license audit or legal certification.

Backend lock SHA-256:
`5ef9aa891893af9e5b582cee539e2b54f04a3345e87f283c5cf2482d726c4c19`.
Frontend lock SHA-256:
`d5eb71b4e859e2531de3f5cf025c01c9213c6556085c44adbd2bb72a851e942a`.
The frontend lock change only records the engine range, not dependency versions.

Author/committer metadata uses the repository-local neutral identity; an older
neutral address is unchanged. All reachable objects, including reflog reachability
and internal tree refs, were scanned for personal identities/paths, development
attribution, credential patterns, five generated credential markers and **12
representations of three keys**. The code-gate scan covered **71 commits / 1,111
objects** with no matches; the documentation commit is scanned again before completion.
No sensitive backup ref, remote or publication artifact was introduced. Global
Git config and the external private pre-anonymization backup were not touched.

Docker input allowlists and generic ignores exclude keys, DBs/journals, captures
and local environments. The source-only rehearsal contained no such tracked
artifacts. Screenshots/private test evidence remain outside Git. Temporary runtime
resources and keys are removed after validation; sanitized local screenshots,
sample reports and results can be retained for review.

## Screenshot recommendation

All nine existing candidates were visually reviewed: synthetic Northstar only,
no visible credentials/key material, private paths/email, browser profile,
terminal or development UI. Nothing was published or added to Git.

Primary subset: **01 Overview, 02 Request Explorer, 03 Authorization Matrix,
04 Finding detail, 06 Report workspace, 07 standalone report**. Request Explorer
visibly demonstrates redaction. **08 Mobile report** is a useful responsive
supplement; **09 Evidence** suits technical documentation. **05 Attack Chain**
is safe but should be recaptured with its entire ordered path visible before
being a lead image: the existing frame cuts off lower steps. Future publication
should label images as synthetic and recheck the exact selected files.

## Remaining issues and decision

### Release blockers

None found in the exercised, documented **single-operator local** release scope.
Publication requires a new explicit instruction; this gate does not authorize
push, tag, release or deployment.

### Acceptable documented limitations

- No workspace authentication, multi-user isolation or supported public/network
  deployment; URL scope is not DNS pinning or an egress firewall.
- Redaction is conservative and incomplete for arbitrary confidential prose;
  exports/old plaintext backups require separate protection and manual review.
- Key loss is unrecoverable. No rotation, rollback resistance, host/root/memory
  protection or forensic erasure guarantee; keep key and DB independently.
- Chromium only; physical print, third-party Markdown viewers and live Linux/Windows
  native stores not exercised. No external security/accessibility certification.
- Bounded scale, unchanged original lab limits, known deprecations; remote CI awaits
  publication. Immutable JSON does not promise identical future renderer formatting.
- Direct-package advisory/license review is not a full transitive or OS-image audit.

### Post-v1 improvements

Broader browser/accessibility/print/platform coverage, designed key rotation,
larger-data profiling, deprecation cleanup, resolved-address controls and complete
dependency/SBOM coverage. None is started by this audit.

Next recommended task: **Public GitHub RC Publication**, only after explicit
authorization. Create the repository, push sanitized history, verify remote
privacy/CI, add approved screenshots/README presentation, choose version/tag only
after green checks, create and verify the release, then freeze scope.
