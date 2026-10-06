# Secret storage

## Threat model and architecture decision

The protection boundary is a copied database, database volume, backup, or
application data directory **without its independently supplied key**. It does
not protect an unlocked backend, host administrator, trusted-account arbitrary
code execution, memory inspection, compromised OS key store, an attacker holding
both assets, or an operator's deliberate plaintext export. This is local
encryption at rest, not end-to-end or zero-knowledge encryption.

The schema audit starts at revision `0006`. Required coverage is broader than
recognizable password fields: arbitrary HTTP data and secret-bearing paths can
also occur in derived records and indexes. The implementation uses **SQLCipher
4 page encryption**, through the maintained `sqlcipher3` binding, rather than
introducing a field-by-field encryption list with plaintext search shadows.
This retains SQLite indexes, SQL filtering, stable IDs, relationships, and
searchable operator prose inside the trusted unlocked backend. ORM request-list
queries select metadata instead of materializing HTTP bodies, headers, redirects
or crawl errors. Detail/replay operations remain separate. Full-history search,
source filters, totals, stable pagination and stale-result guards are preserved.

SQLCipher provides AES-256-CBC encryption with independent per-page HMAC-SHA512
authentication and fresh random IVs. This is SQLCipher's established
authenticated construction, **not AES-GCM**, and no cryptographic primitive is
implemented here. Python `cryptography` is not needed for this database-level
boundary. The storage format is SQLCipher's versioned format 4; application
policy metadata records format/key identity inside the encrypted database.
There is no custom per-field ciphertext envelope or row-level AAD. Page-context
authentication does not provide protection against rollback to an older valid
database. See [SQLCipher design](https://www.zetetic.net/sqlcipher/design/) and
the [Python binding](https://github.com/coleifer/sqlcipher3).

## Persistence classification

| Class | Current persistence | Decision |
| --- | --- | --- |
| Authentication secrets | `identities.bearer_token`, `api_key_value`, `cookies`, `custom_headers`; captured request/response headers | Protected by encrypted database pages; ordinary API redaction remains mandatory. |
| Raw HTTP | `http_exchanges` headers, bodies, URL/query, redirects, error text, including imports, replay, and crawler traffic | Protected from the first persistent write; detail/replay/analysis load payloads only when needed. |
| URL and derived application data | Scope paths; Attack Surface keys/paths/metadata; run target/current URLs; discovery canonical URLs; form actions/field metadata; observation details; comparison results | Also protected, including indexes. URLs and arbitrary response values cannot reliably be classified by secret-name heuristics alone. |
| Operational metadata | Methods/statuses/timestamps, host, source, IDs/FKs, counters, sequences, lifecycle states | Usable by SQL when unlocked, but not exposed as plaintext on disk. No plaintext search-shadow database. |
| Operator-authored content | Engagement/Identity descriptions; Findings, Notes, Retests, Attack Chains and lifecycle history | Remains ordinary searchable text to the application, covered by the same database boundary without field-level API changes. Automated paths retain existing redaction. |
| Evidence | Immutable redacted snapshots and source references | No hidden raw backing copy was found. Immutability/redaction stay unchanged; page encryption additionally protects incidental sensitive prose. |
| Original import sources | Import batches store filename, digest, counts, warnings, and provenance, not the original HAR/cURL/OpenAPI source blob | Keep canonical data only; do not add a duplicate raw source archive. Digests/indexes are inside the encrypted database too. |

All ORM models and the import, replay, crawler, normalization, Candidate,
Evidence, Finding, and Attack Chain persistence paths were reviewed. Source
format parsers canonicalize in memory. Recognition-based UI redaction cannot
identify every private application value; it is not the encryption boundary.

## Implementation sequence

1. Explicit key-provider interface, secure initialization, and authenticated
   database opening with no provider fallback or automatic key replacement.
2. Protected application/migration connections, storage policy revision `0007`,
   and metadata-first HTTP lists with preserved full-history search/pagination.
3. Offline legacy export into a verified fresh encrypted file, restricted
   external backup, atomic replacement, and active SQLite artifact cleanup.
4. Wrong/missing-key, tamper, restart/copy, byte-scan, regression, Docker, and
   browser validation before claiming the milestone complete.

The normal native provider uses an explicitly selected supported OS key store,
not an arbitrary keyring fallback. Docker uses a read-only mounted key file
outside its database volume. Tests inject fresh random in-memory key material.
Key generation is an explicit operator action; normal startup never invents a
replacement key. Key-file permissions and separation from database/repository
paths are checked. Key loss makes protected content unrecoverable.

Migration is an explicit offline operation, separate from routine schema
upgrades. Existing plaintext remains available until an encrypted replacement
has passed integrity, schema, and data comparisons. Backups are sensitive and
must remain outside the application data directory and repository. Migration
does not promise forensic erasure from SSD storage, snapshots, or old backups.
Python likewise cannot guarantee wiping immutable strings/bytes from memory.

Rotation is not part of this milestone; no partial rekey workflow is offered.

## Providers and key lifecycle

`FAULTWEAVER_KEY_PROVIDER` selects exactly `native` (default) or `file`. There
is no fallback chain. Supplying a file path while selecting `native` is a
configuration error, not an implicit switch. Tests inject `MemoryKeyProvider`
programmatically with a fresh random key per workflow; no environment setting
enables a fixed or universal test key. A missing key fails before initialization.
Wrong keys, invalid policy versions and failed page authentication fail closed.

Native storage explicitly selects macOS Keychain, Linux Secret Service or
Windows Credential Manager; third-party keyring discovery is not used. The
service is `Faultweaver`, default account `local-storage-v1`. Set
`FAULTWEAVER_KEYRING_ACCOUNT` to isolate installations. An available, unlocked
OS store is required. Headless Linux can explicitly select the file provider.
macOS grants access according to Keychain policy for the Python executable;
this is not a security boundary against other code running as the same user.
See [keyring security considerations](https://keyring.readthedocs.io/en/latest/#security-considerations).

```bash
# Fresh native installation, once only:
uv run --project backend faultweaver-storage init-key
# Explicit recovery export; keep on a separate private/offline key-backup asset:
uv run --project backend faultweaver-storage backup-key --output /absolute/key-recovery/master.json
```

The documented file workflow uses an explicit absolute path and requires POSIX owner-only permissions
(`0600`), a regular nonsymlink file, and separation from the database directory
and every Git repository. The current non-root operator must own the file.
Non-POSIX file-key mode fails rather than pretending mode bits implement ACLs.
The file contains versioned JSON and 32 cryptographically random bytes encoded
as base64. This encoding is **not** encryption; possession of the key and DB
permits decryption. Generation uses exclusive creation, file and directory
sync, and never overwrites an existing key.

```bash
export FAULTWEAVER_KEY_PROVIDER=file
export FAULTWEAVER_MASTER_KEY_FILE=/absolute/private/faultweaver-keys/master.json
uv run --project backend faultweaver-storage init-key
uv run --project backend uvicorn faultweaver.app:app --reload
```

To recover, stop the backend, restore the encrypted database, and point the
explicit file provider at the independently retained original key backup. Run
`faultweaver-storage check` before starting the API. That check requires the
backend to be stopped and authenticates every page. Never run `init-key` to
recover an encrypted database: it refuses an existing protected database, and
a newly generated key cannot decrypt it. Without the original key or its backup,
the protected content is unrecoverable. Back up both assets, but separately;
copying an entire home directory may collect both and is outside this threat model.

## Legacy migration

Schema upgrades alone do not encrypt plaintext SQLite. The packaged Alembic
head is `0007`; schema-only migration helpers remain available for legacy
maintenance/tests, whereas application startup always supplies a keyed
SQLCipher connection. A separate offline conversion is mandatory for plaintext.

1. Stop the API, all workers and all external SQLite clients. Only one process
   may use a database at a time; the API, check and converter share a process
   lock. Do not remove a live `.lock` file. Multi-worker Uvicorn is unsupported.
2. Explicitly initialize the intended native/file key if no key exists yet.
3. Choose a **new**, restricted backup path outside both the repository and
   active data directory. It must not be the key-backup location. The backup
   is plaintext, sensitive, and `0600`; keep it offline with restricted access.
4. Run the converter with the same database URL and key-provider configuration:

```bash
uv run --project backend faultweaver-storage migrate --backup /absolute/offline-database-backups/legacy.db
uv run --project backend faultweaver-storage check
uv run --project backend uvicorn faultweaver.app:app --reload
```

The converter acquires exclusive SQLite access, consolidates committed WAL
content, switches off WAL, checks legacy integrity, and makes the explicit
backup. It uses SQLCipher's `sqlcipher_export` into a fresh private encrypted
file, not an in-place plaintext rekey. Before atomic replacement it verifies
every table's row count, exact typed-row/schema digest, page authentication and
SQLite integrity. IDs, relationships, source links and stored values are
preserved. Startup then upgrades schema `0006` to `0007` and records encrypted
policy version 1, cipher format 4 and a nonsecret key fingerprint.

The old database stays in place until verification succeeds. On failure before
replacement, retain the original and private backup; correct the cause and retry
with a **new backup filename**. Existing backups are never overwritten. An
already encrypted database is checked and left intact, making retry after
replacement safe; normal startup completes any pending schema upgrade. The
converter refuses remaining legacy WAL/SHM/journal sidecars before replacement.
The compact encrypted replacement has no old plaintext freelist; new writes,
rollback journals and WAL are encrypted, and temporary SQLite data stays in
memory. A crash may leave an encrypted conversion temporary file, not a second
plaintext source. No tool promises secure erasure of old blocks, filesystem
snapshots, historical exports, old volumes or the intentionally retained backup.
Delete/archive those assets according to the operator's retention policy only
after independently verifying recovery.

### Docker

Compose requires `FAULTWEAVER_MASTER_KEY_FILE` to name an existing host key
outside the repository/data volume. The secret mount is read-only at
`/run/secrets/storage-key`; only its path, never its bytes, is in environment
configuration. Neither image nor data volume contains a key copy. Because
owner-only host bind mounts cannot be read by an arbitrary container UID, a
short bootstrap reads the key as root, clears supplementary groups, and drops
permanently to `nobody` (UID/GID 65534) before starting the API. Docker/root
administrators can still read the mounted key; they are excluded adversaries.
The API binds only to host loopback through Compose. Do not relax key permissions
to make a mount work.

For an existing plaintext volume, first back up according to your retention
policy and stop the services. Create a separate host backup directory, private
to its operator, then run the explicit administrative conversion:

```bash
docker compose stop api web
docker compose run --rm --no-deps --volume /absolute/offline-database-backups:/backup api migrate --backup /backup/legacy.db
docker compose up --detach --wait
```

This offline command runs no server. It reads the same mounted key, creates a
root-owned owner-only backup in the independent mount, verifies conversion, and
assigns only the resulting database/lock to the API user. Access to this backup
may require host/container administrator privileges. Retain that plaintext
backup separately, not in the data volume. A failed conversion reports failure;
do not start a new empty volume or generate a replacement key to suppress it.

## Dependency and implementation review

`sqlcipher3==0.6.3` supplies self-contained SQLCipher wheels for supported Python
platforms; the verified macOS arm64/Linux arm64 runtime is SQLCipher 4.12.0 and
SQLite 3.51.1. The binding is Zlib-licensed, SQLCipher is BSD-style licensed;
`keyring` 25.7.0 is MIT-licensed. Their notices remain in installed distributions.
There is no additional application cipher or custom key derivation. Linux
Secret Service brings `cryptography` transitively, but application page protection
is implemented by SQLCipher. All resolved dependencies are locked in `uv.lock`.
See the [binding release metadata](https://pypi.org/project/sqlcipher3/) and
[SQLCipher API](https://www.zetetic.net/sqlcipher/sqlcipher-api/).

No raw source import archive, plaintext search shadow, credentials table outside
the encrypted file, or app-local master-key fallback is introduced. Request
lists are metadata-only at the ORM/API boundary; SQLCipher still necessarily
decrypts the database pages containing the selected columns inside its cache.
Candidate lists omit original/replay payloads and comparison result bodies;
the auth matrix selects only IDs, methods, hosts, paths and response statuses.
Evidence lists and chain evidence links select metadata; an Evidence snapshot
is loaded only when selected, with stale-selection results discarded. Detail
endpoints retain their complete redacted representation. Operator-authored prose
remains usable. No application-level decrypted history cache was added.
Full page integrity checks occur at startup, so startup cost grows with database
size. Runtime UI payloads do not contain keys, key fingerprints or ciphertext.

## Validation results

Validated on 2026-10-06 using synthetic data only. No external target, credential
attack, scope exception, crawler-safety relaxation or target-specific production
logic was introduced.

| Capability | Result | Evidence / limit |
| --- | --- | --- |
| Authenticated storage and fresh writes | Validated | Round trip, independent random representations, ciphertext/IV/tag tamper and page-position substitution rejection. |
| Key separation and stolen DB | Validated | Plain SQLite cannot read the copied file; missing/wrong keys fail without changing bytes; correct key recovers content and replay. Master bytes, hex, base64 and serialized material absent from scanned data artifacts. |
| Native macOS provider | Validated | Real unique Keychain entry initialized, read and removed; fake-backend tests also cover unavailable store and no replacement. |
| Native Linux/Windows providers | Not exercised | Explicit native implementations configured, but no live desktop key store on those platforms was available. |
| File and test providers | Validated | Owner-only regular nonsymlink files outside Git/data; explicit random ephemeral injection for backend/demo/compatibility tests; invalid/missing files and conflicting provider selection reject. Non-POSIX file mode intentionally fails. |
| Legacy conversion | Validated | Current plaintext schema with bearer/cookie/password/request/response/query markers; exact schema/typed rows/counts preserved; replay/import/Identity/redaction work after conversion and schema upgrade. |
| Interrupted migration | Validated | Failed replacement and failed digest verification preserve recoverable originals; new-backup-path retry succeeds. Crash-left committed WAL is consolidated by SQLite; no old WAL/SHM/journal remains in the active directory. |
| Raw-byte protection | Validated | Marker scans of live database, encrypted WAL/SHM, rollback journal, deleted pages, post-migration and Docker data artifacts. Restricted plaintext migration backups intentionally retain data outside that boundary. |
| Native and Docker restart | Validated | Same key recovers Identity replay, imports, completed baseline, findings, immutable evidence, chains and retests. Docker missing/wrong keys refuse startup with unchanged database hash. |
| Docker offline migration | Validated | Independently mounted backup, exact schema/row comparison, encrypted named-volume replacement, UID 65534/mode 0600. Docker Desktop bind UID mapping also checked through actual unprivileged access. |
| Metadata-first workspace | Validated | SQL column-selection assertions cover Requests, auth matrix, Candidates, Evidence, Findings, Retests and Attack Chains; HTTP payloads, comparison bodies and Evidence snapshots are absent from list queries. |
| Demo workflow | Validated | Bounded discovery, two identity comparisons, candidate promotion, immutable evidence, validated two-finding chain, truthful Still Vulnerable retest and restart. No fixed target state was fabricated. |
| Juice Shop / DVWA / WebGoat / Mutillidae | Validated | One existing workflow per target passed under encrypted storage. All previous Partially validated / Not exercised / Not applicable capability limits in their reports remain in force. |
| Responsive Chromium | Validated | Ten populated workspace views at 1440×1000, 1024×900, 768×900 and 375×812; pagination past 100, full-history search, detail and selected Evidence loading; zero page/console errors, secret markers or horizontal page overflow. |
| Per-field envelope / AAD | Not applicable | SQLCipher authenticated pages were selected instead; policy/cipher/key-identity mismatch and page-context tests cover this design. |
| Rotation | Not exercised | Not implemented; restore requires the original key. |
| Forensic erase, rollback prevention, compromised backend/root | Not applicable | Explicitly outside the storage threat model; no claims made. |

Engineering checks: **107 backend + 5 demo = 112 tests**, including migrations;
**18 frontend tests / 8 files**; Ruff lint/format **122 Python files**; Svelte
**0 errors / 0 warnings**; locked uv/npm installs; production frontend and
API/web/demo Docker builds; npm audit **0 vulnerabilities**. The existing
Starlette/SQLite deprecations and host Node 25/Vitest engine warning remain;
the Docker frontend uses Node 22. External compatibility runners remain opt-in,
outside normal CI. CI now invokes the explicit backend/demo suites through
`python -m pytest`, avoiding host path-dependent demo import behavior.

The release-hygiene scan covers tracked content, all reachable Git objects
(including local tree snapshots), commit identities and local reflogs. No
generated validation key/secret, personal identity/path or development-provenance
marker was found. Public synthetic demo fixtures are intentional, not live
credentials. This scan is not a proof that arbitrary operator data is safe to
publish; raw captures, plaintext migration backups and keys remain private assets.

### Performance

Same machine/runtime, pre-milestone source exported without changing Git refs,
and current source; 150 synthetic replay records, 4 KiB JSON responses, mocked
transport, median of seven runs (three for comparisons). Times are milliseconds,
not production throughput guarantees. The startup/full-integrity scan is not
part of these steady-state measurements.

| Operation | Before | Protected storage |
| --- | ---: | ---: |
| Request Explorer 100-row API page | 9.30 | 5.28 |
| HTTP detail | 1.12 | 1.13 |
| Raw HTTP import | 3.39 | 4.01 |
| One-entry HAR import | 4.16 | 7.73 |
| Replay | 2.81 | 3.40 |
| Response comparison | 2116.50 | 2110.00 |

Metadata projection reduces the list payload. Small import/replay overhead is
measurable; no material comparison slowdown appeared in this sample. Larger
real datasets and startup scaling are **Partially validated**, not a capacity
claim. Mutillidae's similar-HTML comparator still took **25.701 seconds**;
its complete compatibility workflow took **60.56 seconds**. The earlier manual
browser observation was about 25.5 seconds for comparable-sized HTML, not an
identical controlled input. That pre-existing algorithmic cost remains a later
targeted performance task; normalization and candidate thresholds were unchanged.
