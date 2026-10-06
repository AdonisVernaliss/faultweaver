# Professional reporting

Reports are engagement-scoped deliverables, not scans. Only operator-confirmed
Findings and selected Attack Chains are report material. Unconfirmed, rejected,
false-positive and informational-only Candidates are never promoted implicitly.
An Informational **Finding** is a confirmed record and can be included.

## Operator workflow

1. Open **Report**, create a named `REP-###` draft and author Executive Summary,
   Methodology, Limitations and Conclusion in plain text. No conclusions or fixes
   are invented. Numbering is independent per Engagement.
2. Review actual configured scope and completeness notes. Missing optional prose
   is reported, not fabricated. Ready/generation requires active scope; discovered
   URLs do not expand authorization.
3. Select Findings and Attack Chains. Defaults follow all eligible records until
   individual selection. Informational Findings are included by default; archived
   records and Draft chains need explicit opt-in. A default chain missing a
   selected Finding is skipped with a warning; explicit chain selection requires
   all its Findings. Fixed/Accepted Risk remain Findings, with unchanged severity.
4. Review Retests: latest means greatest test timestamp, then sequence. Include
   history or latest only. Not Retested is not counted as a retest. Preserved
   Finding Evidence includes original and later supporting snapshots; each Retest
   separately references its Evidence. Reusing a snapshot never removes it from
   the Finding. The model has no exclusive original/retest role, so none is guessed.
5. **Save draft** or **Mark ready**, then **Preview / Export**. Preview shows saved
   prose with current sources, marked DRAFT PREVIEW. Save edits before preview or
   generation. Completeness notes do not certify assessment quality.
6. **Generate revision** freezes a canonical document in encrypted storage.
   Download HTML, Markdown or JSON from the selected preserved revision. Subsequent
   source/draft edits do not modify previous revisions or regenerate old downloads.

Draft → Ready → Generated is an operator workflow, not mandatory approval.
Editing Generated returns to Draft. Archive preserves exports; restore before
editing/generating. Stale saves fail with 409 and require reloading. Unsaved report
edits are guarded when switching views, Engagements, reports or leaving the page.

## Format contract

All three formats derive from **one canonical document**. JSON schema version is
`1.0`, renderer version `1`; `GET /api/report-schema` describes the contract.
JSON has stable key order, UTF-8 text and deterministic bytes per preserved
revision. Metadata includes application version, generation time, IDs and a
canonical JSON SHA-256. Findings sort by Critical/High/Medium/Low/Informational,
then sequence; chain steps retain explicit positions.

The frozen artifact is canonical JSON. HTML/Markdown are rendered on download by
the installed renderer, deterministically within that version. Byte identity after
a future renderer upgrade is not promised; keep delivered files if exact formatting
must be retained. Ordinary source edits and restarts do not change current exports.

Sections include executive summary, scope, methodology, limitations, overview
table, Finding detail/remediation, ordered chain paths, retest history, conclusion,
Evidence appendix, assessment metadata and review notes. No aggregate risk score,
coverage percentage or compliance claim is inferred.

HTML works offline with system fonts, embedded CSS, internal navigation, wrapping
HTTP blocks/tables and print styles. No scripts, external fonts or network assets.
Browser printing to PDF is possible; no native PDF export or pagination engine is
implemented. Markdown contains escaped prose and fenced technical excerpts. JSON
consumers must validate the schema and escape values for their presentation context.

## Security and limits

Report creation/generation sends no target traffic and reads no live HTTP or
Identity payloads. Evidence comes only from immutable redacted snapshots, never
mutable sources. Lists/options fetch metadata instead of full report/snapshot
payloads. Generation uses a consistent transaction and a versioned draft.

HTML escapes all arbitrary text; reference URLs are printed rather than used as
executable links. Markdown escapes prose and uses fences longer than captured
backtick runs. Preview uses an empty iframe sandbox; offline HTML also carries
restrictive CSP. Downloads use no-store/nosniff and validated filenames such as
`faultweaver-REP-001-r1.html`, never titles/paths. No server export-path API exists.

Recognized credentials are redacted again at export. Authentication/session
headers are excluded; only selected useful metadata is rendered. Each excerpt is
limited to 3,000 characters with a truncation marker. Canonical documents are
limited to 10 MB, selections to 1,000 records per query (200 explicit chain IDs),
and Evidence/Retest content to 2,000 records. Large-data memory/scaling is not a
streaming export guarantee.

**Exports are confidential plaintext outside SQLCipher.** Arbitrary prose,
application values and URLs may remain private despite redaction. Review before
sharing. Encryption cannot protect downloaded files or an unlocked compromised
host. See [Security](../SECURITY.md).

## Exact HTML-comparison optimization

Profiling identified `SequenceMatcher.find_longest_match`, not SQLCipher or
normalization, as the previous similar-HTML bottleneck. Equal texts now return
1.0 directly. Other comparisons retain difflib recursive blocks, tie order and
ratio, using a suffix automaton over the smaller interval for the inner search.
No junk heuristic, sampling, truncation, response cache or dependency was added.
Normalization, JSON differences and Candidate thresholds are unchanged.

Tests compare exact blocks/ratios across all binary strings of length 0–5 and
1,000 seeded Unicode/repetition/range cases. A deterministic 51 KB HTML regression
guards against the previous tens-of-seconds delay. Measurements and the memory
tradeoff are in [release validation](release-validation.md).
