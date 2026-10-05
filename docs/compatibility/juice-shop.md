# OWASP Juice Shop compatibility

Faultweaver was validated locally against stock **OWASP Juice Shop 20.2.0** for
the workflows listed here. This is a bounded compatibility statement, not a
claim of complete Juice Shop support or vulnerability coverage.

## Validated distribution

- Image: `bkimminich/juice-shop:v20.2.0`
- Digest: `sha256:8739101ade29358abb5469ee66ae78e582c97ed0a5543a4ad102e5fa5193526b`
- OCI source: `https://github.com/juice-shop/juice-shop`
- Validation date: 2026-10-05
- Publication: `127.0.0.1:3008:3000` only

The compatibility Compose file uses the tag and digest together. Juice Shop is
not a Faultweaver runtime dependency, its source is not vendored, and the target
is not modified.

## Reproducible validation

The complete compatibility check is explicit and separate from the normal test
suite:

```bash
make compatibility-juice-shop
```

The command starts the pinned image when the compatibility Compose project is
not already running, waits for its health check, runs the isolated test, and
removes only the Compose resources it started. An already-running service owned
by that Compose project is reused and left running.

For an interactive session:

```bash
make compatibility-juice-shop-up
make compatibility-juice-shop-test
make compatibility-juice-shop-down
```

`FAULTWEAVER_JUICE_SHOP_PORT` can select another loopback host port. The test
refuses non-loopback and non-HTTP targets. It creates two random synthetic
`example.test` users, keeps generated passwords and session tokens in memory,
uses an isolated temporary Faultweaver database, and does not retain raw HAR or
credentials in the repository.

## Compatibility matrix

| Capability | Result | Observed validation |
| --- | --- | --- |
| Baseline crawler | Partially validated | The HTML shell, `robots.txt`, and sitemap were handled within exact scope. JavaScript was not executed, forms were not submitted, and SPA API coverage remained intentionally incomplete. |
| HAR import | Validated | A real Chromium HAR imported as `IMP-001`: 60 records, 59 HTTP transactions with responses, one WebSocket record skipped, and binary bodies omitted with explicit warnings. |
| cURL import | Validated | A browser-style cookie-authenticated `whoami` command previewed redacted and imported as `IMP-002`; it was parsed, never executed during import, and replayed only after an explicit action. |
| Request Explorer | Validated | 67 real crawler/import/replay exchanges remained usable with long API paths, query strings, JSON, and redacted cookie material. |
| Attack Surface | Validated | 47 concrete entries retained crawler/HAR/cURL provenance. `/rest/user/whoami` retained both HAR and cURL sources without aggressive numeric-path generalization. |
| Replay | Validated | A normal request was replayed with the selected synthetic session identity and persisted separately from the original. |
| Identity contexts | Validated | Anonymous, `user-a`, and `user-b` were engagement-scoped; session-cookie values remained redacted from ordinary API/UI output. |
| Response comparison | Validated | The same normal authenticated operation was replayed for two synthetic users and produced a persisted structured JSON comparison. |
| Authorization matrix | Validated | The imported original recorded separate observed 200 cells for anonymous, `user-a`, and `user-b`, each linked to its own replay evidence. |
| Candidate workflow | Validated | The identity comparison correctly produced no automatic authorization Candidate. A real passive CSP Candidate was manually reviewed and promoted without weakening conservative heuristics. |
| Finding | Validated | The confirmed missing CSP response header was recorded as `FW-001` with complete operator-authored impact, reproduction, remediation, and reference fields. |
| Evidence | Validated | The comparison and confirmed response were captured as redacted immutable `EV-001` and `EV-002` snapshots and survived an API restart. |
| Attack Chains | Partially validated | `FW-001` and `EV-002` participated in Draft `AC-001`. No second related reproduced finding existed, so no artificial multi-finding chain was authored or validated. |
| Retest | Not applicable | The intentionally vulnerable target was not modified to manufacture a fixed-state retest; the subsystem remains covered by the normal suite. |
| OpenAPI | Not exercised | No target contract was used in this validation. |

## Real workflow

The interactive validation used ordinary application behavior only:

1. Start the stock pinned container on loopback.
2. Create two synthetic users through the browser and sign in normally.
3. Browse products, add an item to the first user's own basket, open that basket,
   and request each user's own identity endpoint.
4. Capture a temporary full Chromium HAR outside the repository.
5. Authorize exact `http://127.0.0.1:3008/` scope and complete bounded
   `RUN-001` with 3 requests, 2 pages, 3 endpoints, 1 observation, 1 conservative
   Candidate, and 0 failed requests.
6. Preview/import the HAR and a representative copied cURL command.
7. Inspect real traffic and provenance, create three Identity contexts, replay a
   normal request, and compare the two synthetic authenticated responses.
8. Confirm the passive CSP observation as `FW-001`, preserve comparison/response
   evidence, and verify that the finding can participate in a Draft Attack Chain.
9. Restart the Faultweaver API and verify the run, imports, comparison, finding,
   evidence, and chain remain available.
10. Walk Requests, Attack Surface, Authorization Matrix, Findings, Evidence, and
    Attack Chains in Chromium at 1440x1000, 1024x900, 768x900, and 375x812.

No access-control vulnerability, challenge solution, scoreboard integration,
brute force, destructive action, or cross-user data access was used.

## Browser and redaction results

All four viewports had zero page-level horizontal overflow, console errors, page
errors, failed browser requests, or unexpected HTTP error responses. The real
browser HAR contained no duplicate header names, so duplicate-header behavior
was not established from this sample; it remains covered by the generic HAR
parser tests. Captured authentication headers and cookies rendered as
`[REDACTED]` in previews, Request Explorer, comparisons, identities, findings,
and evidence.

## Known limitations

- The conservative URL crawler does not execute JavaScript and cannot enumerate
  complete SPA/API behavior. HAR, cURL, raw HTTP, and applicable API contracts
  remain the intended complementary acquisition paths.
- HAR WebSocket records are skipped because the canonical import model accepts
  HTTP and HTTPS transactions. Binary response bodies are represented as
  omitted rather than copied into operator-safe views.
- Compatibility is established only for Juice Shop 20.2.0 and the workflows in
  this document. Mutillidae II remains unvalidated.
- The real identity comparison exercised expected per-user behavior and did not
  generate a Candidate. This is the intended conservative outcome.
- Replay credentials and captured traffic remain unencrypted at rest in the
  local SQLite database. The database and any raw local capture must be treated
  as sensitive and removed when no longer needed.
