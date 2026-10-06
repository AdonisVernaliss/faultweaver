# Damn Vulnerable Web Application compatibility

Faultweaver was validated locally against stock **Damn Vulnerable Web
Application (DVWA) 2.5** for the workflows listed here. This is a bounded
compatibility statement, not a claim of complete DVWA support or vulnerability
coverage.

## Validated distribution

- DVWA image: `ghcr.io/digininja/dvwa:a96943d`
- DVWA digest: `sha256:d8e960e0e3ca2aa487532b404a6af2669f46854a74b5182f2f8e0e31895e0e29`
- DVWA release commit: `a96943d` (release 2.5)
- DVWA platform: `linux/amd64`
- Database image: `docker.io/library/mariadb:10`
- Database digest: `sha256:7db29378d4fdab73f8123bbc2b48905c90d1a4b00cf848b028f1e81e623257f2`
- Validation date: 2026-10-05
- Publication: `127.0.0.1:4280:80` only

Both images are pinned by tag and digest. DVWA is not a Faultweaver runtime
dependency, its source is not vendored, and its image is not modified. The
compatibility runner creates a fresh ephemeral database, initializes it through
the ordinary setup form, and replaces the stock fixture account in that database
with one synthetic username and a random in-memory password. The database has no
host-published port and is removed with its volume after the run.

The 2.5 image is published for `linux/amd64`; the Compose file declares that
platform explicitly, so non-amd64 hosts require Docker's platform emulation.

## Reproducible validation

The complete compatibility check is explicit and separate from the normal test
suite:

```bash
make compatibility-dvwa
```

The command generates random database and application passwords in memory,
starts a fresh dedicated Compose project, waits for both services to become
healthy, initializes DVWA, runs the isolated compatibility test, and removes its
containers, network, and volume even when the test fails. It refuses to reuse an
already-running compatibility project. `FAULTWEAVER_DVWA_PORT` can select another
loopback host port. The test rejects non-loopback and non-HTTP target URLs.

No passwords, session identifiers, raw HAR files, database files, or screenshots
are retained in the repository.

## Compatibility matrix

| Capability | Result | Observed validation |
| --- | --- | --- |
| Baseline crawler | Partially validated | `RUN-001` completed against the anonymous login page with bounded exact scope. Only GET requests were sent and no discovered form was submitted; authenticated crawling was intentionally not added. |
| HTML form discovery | Validated | The login POST form and its fields were discovered. The hidden `user_token` field retained `hidden=true` and `has_value=true` metadata without exposing or submitting the value. |
| HAR import | Validated | The automated seven-transaction capture previewed and imported 7/7 request/response pairs. A separate real Google Chrome capture imported 32/32 records with no skips. |
| cURL GET | Validated | A cookie-authenticated GET with query parameters and a hidden-token parameter previewed and imported as `IMP-002`; import did not execute it. |
| cURL POST | Validated | A cookie-authenticated POST to `/security.php` previewed and imported as `IMP-003`; import did not execute it. |
| URL-encoded bodies | Validated | `application/x-www-form-urlencoded` bodies remained parseable while password and token fields were redacted with the generic sensitive-key policy. |
| Cookies/session state | Validated | `PHPSESSID` and `security` cookies supported normal authenticated replay through scoped Identity contexts; values were redacted from API and persisted operator-safe output. |
| Request Explorer | Validated | Crawler, HAR, cURL, and replay traffic was searchable with methods, paths, status, provenance, redirects, and redacted request material intact. |
| Attack Surface | Validated | GET and POST entries retained combined HAR/cURL provenance for `/vulnerabilities/xss_r/` and `/security.php`. |
| Replay | Validated | Explicit POST replay used the selected synthetic Identity, followed the normal 302 redirect, and persisted the resulting GET/200 exchange and redirect chain. |
| Response comparison | Validated | Authenticated and anonymous HTML responses both returned 200, normalized below 0.95 similarity, recorded a redirect difference, and persisted a structured comparison. |
| Authorization matrix | Validated | The compared request produced distinct authenticated and anonymous 200 cells linked to their replay observations. |
| Candidate workflow | Validated | The identity comparison correctly produced no automatic authorization Candidate. A passive missing-CSP Candidate was reviewed, accepted, and promoted without relaxing conservative heuristics. |
| Finding | Validated | The accepted passive observation became low-severity `FW-001` with operator-authored impact, reproduction, remediation, affected asset, endpoint, and reference. |
| Evidence | Validated | The comparison and source response became immutable redacted `EV-001` and `EV-002` snapshots and survived an API restart. |
| Retest | Not applicable | The stock intentionally vulnerable target was not changed to manufacture a fixed-state retest; the retest subsystem remains covered by the normal suite. |
| Attack Chains | Not exercised | Only one confirmed passive finding existed, so no artificial multi-finding relationship or chain was created. |

## Real workflow

The compatibility validation used ordinary application behavior only:

1. Start the pinned DVWA and MariaDB images on loopback with a fresh volume and
   set DVWA's security level to `impossible`.
2. Initialize the database through DVWA's setup form, then use an ephemeral
   synthetic account for normal sign-in.
3. Load the reflected-input form with benign text, read its hidden CSRF field,
   and submit the security-level form without changing the configured level.
4. Build and import a response-bearing HAR from those real HTTP exchanges.
5. Preview and import representative copied cURL GET and URL-encoded POST
   commands using separate authenticated sessions.
6. Run a bounded anonymous baseline against `/login.php`, inspect discovered
   form metadata, and verify crawler requests remain GET-only with no bodies.
7. Inspect Request Explorer and Attack Surface provenance, create anonymous and
   synthetic cookie-backed identities, replay the normal form request, compare
   authenticated and anonymous responses, and inspect the Authorization Matrix.
8. Preserve comparison evidence, review and promote the passive missing-CSP
   Candidate, attach response evidence, and restart the API to verify persistence.
9. Independently navigate the real Faultweaver UI in Google Chrome at
   1440x1000, 1024x900, 768x900, and 375x812 while inspecting Requests, Attack
   Surface, Authorization Matrix, Candidates, Findings, and Evidence.

No DVWA vulnerability module was exploited. The validation did not brute-force
credentials, access another user's data, modify the target source or image,
escape a container, create persistence, evade controls, or send traffic outside
loopback.

## Browser and redaction results

The independent Chromium capture imported as `IMP-004` with 32 total records,
32 accepted responses, and zero skips. At every tested viewport the inspected
pages had zero document-level or Request Explorer horizontal overflow, console
errors, page errors, failed browser requests, or unexpected HTTP error
responses.

Passwords, `user_token`, cookie headers, and cookie values rendered as
`[REDACTED]` in import previews, Request Explorer, identities, comparisons,
findings, evidence, and restart-persisted API output. The compatibility work
strengthened the generic URL-encoded form redactor by applying the existing
sensitive-key policy to every decoded field name; no DVWA-specific production
logic was added.

## Known limitations

- The crawler validation is anonymous and intentionally conservative. It does
  not sign in, submit discovered forms, execute JavaScript, or enumerate every
  DVWA module.
- Form discovery records that a hidden value exists, not the secret value
  itself. Stateful traffic is acquired through HAR/cURL or explicit replay.
- The automated HAR fixture is assembled from real HTTP responses; the separate
  full Chromium HAR and responsive walkthrough are manual compatibility checks,
  not ordinary CI.
- Compatibility is established only for DVWA 2.5 at the pinned release commit
  and for the workflows documented here. Separate
  [Mutillidae II validation](mutillidae.md) has its own bounded coverage matrix.
- The workflow was rerun with authenticated encrypted storage during
  [Secret-Storage Hardening](../secret-storage.md#validation-results): **Validated**.
  The original coverage limits remain unchanged. Raw external captures and any
  legacy plaintext backups still require separate protection.
