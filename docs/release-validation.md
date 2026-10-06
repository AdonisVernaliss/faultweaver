# Professional Reporting + Release Polish validation

Local validation on 2026-10-06. This is a development milestone, **not a public
release, penetration-test certification or the subsequent full product/security
audit**. No push, tag, public repository, deployment or publication was performed.

## Reporting

Implemented engagement-scoped `REP-###` drafts, operator-authored prose, explicit
Finding/chain inclusion, readiness notes, archive/restore, optimistic version
checks and immutable encrypted canonical revisions. Schema migration `0008` adds
Reports/revisions without rewriting earlier domain data. HTML, Markdown and JSON
share one canonical document. JSON schema `1.0` is available through the API.
See [reporting](reporting.md) for exact semantics and limits.

The synthetic Northstar scenario contained two High, one Low and one Informational
Finding, immutable Evidence, a three-step validated chain and a Still Vulnerable
retest. UI checks excluded Informational content, saved/marked Ready/generated,
downloaded all formats, archived/restored and edited a draft while preserving the
previous revision. Unconfirmed Candidates were not report Findings.

## UI and browser results

Chromium production-build checks used **1440×1000, 1024×900, 768×900 and 375×812**.
There were **88 populated-view checks**, covering the Engagement selector and
overview context, Assessments, Attack Surface, Identities, authorization matrix,
Candidates, Findings, Evidence, chains, Retests, Requests/detail, actual read-only
demo replay/comparison, Import dialog, Report workspace and all six report
subsections including preview. The existing Engagement selector/Assessment
overview were inspected; no separate Engagement-list/overview page was invented.

No page or preview horizontal overflow, JavaScript/CSP errors, unexpected failed
HTTP requests or visible credential markers were found in that final pass. Wide
tables retain contained scrolling where appropriate. Ten empty workspace views,
loading during a delayed Engagement switch, late-response rejection, a controlled
503 Report error and Reload recovery were checked separately. That intentional
503 is not included in the zero-unexpected-failures claim.

Browser review reproduced and fixed stale Assessment details after switching to
an empty Engagement. Panels now reset on Engagement changes, and late Engagement
and request-detail responses cannot overwrite the newer selection. Dialogs move
focus inside, trap Tab/Shift+Tab, close with Escape and restore invoker focus.
An inert settings placeholder was removed and error dismissal labeled.

The Chromium page-wide `networkidle` event did not settle for sandboxed `srcdoc`
despite zero outstanding requests. Validation instead checked completed HTTP
work, a quiet interval and actual rendered frame headings. Sandbox permissions
were not relaxed. The mobile preview was also scrolled into the viewport and
visually inspected; an offscreen iframe screenshot is not treated as proof of
rendering. This is not a WCAG certification or a Safari/Firefox audit.

## Report security

**Validated:** HTML escaping and sandbox/CSP, literal malicious prose, fenced
target content, Markdown fence-break attempts, no active untrusted reference
links, safe filenames, no arbitrary server export path, engagement isolation,
corrupt cross-engagement Evidence-link rejection, recognized secret absence in
all formats, immutable revisions and no HTTP/Identity payload reads for reporting.

Final review moved Evidence-count checks before payload reads. Finding Evidence
references use metadata; selected snapshots are processed one at a time into
bounded excerpts, with an early document-size budget. Retest reuse cannot remove
an original snapshot from the Finding's preserved history. Generated revision
content remains separate from mutable Finding/Retest state.

The real browser verified downloaded filenames, JSON inclusion/counts, escaped
preview content and unchanged old downloads after draft edits. Offline HTML was
opened from disk with network blocked: no outbound assets were requested. Print
media hid navigation, retained wrapping HTTP text and had no horizontal overflow.
Native PDF export is **Not applicable**; physical print/PDF pagination and
third-party Markdown viewers are **Not exercised**.

Workspace headers include nonce-based script CSP, nosniff, no-referrer,
frame-ancestor denial and no-store for dynamic responses. Explicit configured
origins reject wildcard/path/credential/query/fragment forms; blank native-store
accounts fail safely. Existing scope, crawler, redaction and Candidate rules
remain unchanged.

## Performance

Local measurements, not universal budgets or a load-test claim:

| Operation | Measurement | Interpretation |
| --- | --- | --- |
| Deterministic similar HTML, 51,516/51,550 characters | Previous Python matcher 21.4868 s; new five-run median 0.0481 s | Identical unrounded ratio 0.9995536840471154; same fixture, no profiling overhead. |
| Mutillidae similar HTML, 48,020/51,259 normalized characters | New 0.2055 s; score 0.9185 | Pre-change profiled result had the same score and took 47.40 s. Historical unprofiled 25.701 s is not a controlled identical-response benchmark. |
| Equal Mutillidae HTML, 51,618 characters | About 0.025 ms | Exact-equality path; score remains 1.0. |
| Representative HAR import | 100 records / 154,288 bytes in 253.6 ms | New synthetic Engagement, encrypted Docker API, no target request from import. |
| Request list / search | 29.6 / 12.9 ms median of ten API calls | 100 stored records; real `q` search returned one match. |
| Full synthetic report generation | 34.2 ms | Four Findings, four Evidence items, validated chain and retest. |

Profiling attributed almost all old comparison time to difflib's inner search.
The exact replacement preserves matching blocks, earliest-position ties and the
ratio; normalizer and Candidate thresholds did not change. No dependency was
added. The 51 KB comparison used approximately **19.9 MB peak Python allocations**
in a separate traced run. Larger/adversarial shapes may cost substantially more;
the existing response-capture bound remains, and worst-case scaling is only
**Partially validated**. No global sub-second guarantee is made.

## Validation suite

| Check | Result |
| --- | --- |
| Backend | **Validated — 139 passed**, including 18 report cases, migrations, secret storage, exact matching and configuration. |
| Demo | **Validated — 5 passed**; full lifecycle now generates all three formats and compares them after restart. |
| Frontend | **Validated — 31 passed in 11 files**. |
| Ruff / formatting | **Validated — 127 Python files**; clean diff whitespace. |
| Svelte / TypeScript | **Validated — 0 errors, 0 warnings**. |
| Locked dependencies | **Validated — `uv sync --locked`, `npm ci`**. |
| npm audit | **Validated — 0 reported vulnerabilities at check time**; not a full dependency security audit. |
| Production builds | **Validated — native frontend and API/web/demo Docker builds**. |
| Fresh install | **Validated — new random independent key, dedicated empty Docker volume, API/web startup, first Engagement and full report**; no existing developer database used. |
| Previous encrypted schema | **Validated — `0007` → `0008`, preserved Engagement, Report creation/counter, restart and immutable export**; earlier migration coverage retained. |
| Real runtime restart | **Validated — API container recreation with the same independent key; 25 state/export digests identical**, including Findings, Evidence, chain, retest, draft and both reports' HTML/Markdown/JSON. |

The final combined backend/demo invocation passed **144 tests**. Existing
Starlette/httpx and SQLite datetime-adapter deprecations remain. The host Node 25
runtime emits Vitest's engine-range warning; checks passed, and the Docker web
build uses supported Node 22. These are recorded rather than suppressed.

## Compatibility matrix

No lab-specific production code or new vulnerability coverage was added. Existing
one-shot runners remain opt-in, separate from ordinary tests, and clean up only
their own resources. Original target-specific limitations remain authoritative.

| Target / capability | Status | Evidence / limitation |
| --- | --- | --- |
| Juice Shop 20.2.0 existing workflow | Validated | 1 passed, 3.18 s; [original matrix](compatibility/juice-shop.md). |
| DVWA 2.5 existing workflow | Validated | 1 passed, 2.11 s; [original matrix](compatibility/dvwa.md). |
| WebGoat 2026.4 existing workflow | Validated | 1 passed, 3.32 s; [original matrix](compatibility/webgoat.md). |
| Mutillidae II 2.12.8 existing workflow | Validated | 1 passed, 4.23 s; [original matrix](compatibility/mutillidae.md). |
| Reporting lifecycle | Validated | Synthetic Northstar API/UI scenario and isolated unit fixtures, not new exploit testing. |
| Live report authoring against every external lab | Not exercised | Lab reruns validate their existing bounded workflows; Report-specific UI was tested with Northstar. |
| General large-dataset/report scaling | Partially validated | Bounded selections, early Evidence reads and representative metrics; no load certification. |
| Native PDF exporter | Not applicable | No PDF subsystem added; offline HTML has browser print styles. |

## Documentation and dependencies

README now leads with grouped capabilities and a keyed local Quick Start.
Makefile exposes help/install/test/validate/up/demo-up/down without silently
starting lab traffic in normal validation. SECURITY documents no-login local
trust, encrypted storage versus plaintext exports and the absence of an
established private disclosure endpoint. Architecture/storage and report schema,
workflow, limits and confidentiality are documented; CHANGELOG remains Unreleased.

No dependencies or lockfile changes were needed. Direct installed Python licenses
were checked: MIT, BSD-3-Clause and the sqlcipher3 binding's bundled Zlib-style
notice. Direct frontend packages are MIT except TypeScript (Apache-2.0).
Existing distribution notices were retained. This was a direct-dependency review,
not a complete transitive legal/SBOM audit; no third-party source was copied.

## Screenshots, Git and privacy

Nine locally retained candidate captures cover Engagement/Assessment overview,
Request Explorer, authorization matrix, Finding detail, Attack Chain, Report
workspace, standalone report, mobile report and Evidence library. They contain
synthetic data only, with visible request credentials redacted. Candidates were
visually inspected and remain outside Git; the final audit decides publication.

Work uses chronological local commits on `main`, with the repository-local
neutral identity. All reachable objects (including local tree refs),
author/committer metadata, reflogs,
tracked files and current generated key representations were scanned. Known
synthetic API `/api/users/` paths were reviewed as false matches, not home paths.
No personal author identity, private path, real credential or development
provenance finding remained. No sensitive historical backup ref was introduced;
the external private pre-anonymization backup was not inspected or modified.

## Remaining risks and next gate

- **Release blocker/gate:** the independent Full Product + Security Release Audit
  and final publication approval have not occurred. This milestone does not
  authorize a public release or v1.0.0 tag. No blocker remains in the exercised
  reporting workflow.
- **Acceptable local limitation:** no login/multi-user/public deployment support;
  exports can contain confidential arbitrary prose despite credential redaction.
  HTML/Markdown are renderer-version presentations of immutable JSON, not promises
  of byte-identical formatting across future renderer upgrades.
- **Acceptable validation limitation:** Chromium only; no physical print layout,
  cross-platform native key-store rerun, full large-data load test or new lab
  exploit coverage. Existing storage threat-model exclusions and key-loss risk
  remain unchanged.
- **Post-v1 improvements:** large-data scaling, broader browser/print/accessibility
  coverage, deprecation cleanup and any separately designed export formats or
  key rotation. Do not expand scope automatically.

Recommended next task: **Full Product + Security Release Audit**. It has not been
started as part of this milestone.
