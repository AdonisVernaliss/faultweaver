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
searchable operator prose inside the trusted unlocked backend. ORM list queries
will select metadata instead of materializing entire HTTP bodies.

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

Implementation and validation results will be recorded here when complete.
Rotation is not part of this milestone; no partial rekey workflow is offered.
