# OWASP WebGoat compatibility

Faultweaver was validated locally against stock **OWASP WebGoat 2026.4** for
the workflows listed here. This is a bounded compatibility statement, not
complete WebGoat support or vulnerability coverage.

## Validated distribution

- Image: `webgoat/webgoat:v2026.4`
- Multi-platform digest: `sha256:d4ac9fc2b0a41b68d64dedde684f4783aa60cc785838435a6d5bd5a25b387497`
- Release commit: `872d614`
- Published platforms: `linux/amd64` and `linux/arm64`
- Validation date: 2026-10-05
- Publication: `127.0.0.1:4080:8080` only

The official image is pinned by tag and digest. Its source is not vendored and
its image is not modified. WebGoat is separate opt-in compatibility
infrastructure, not a Faultweaver runtime dependency. WebWolf's port 9090 is
not published or exercised. Synthetic users live in the ephemeral container;
the Compose project mounts no persistent volume.

Upstream references: [release v2026.4](https://github.com/WebGoat/WebGoat/releases/tag/v2026.4)
and [official container instructions](https://github.com/WebGoat/WebGoat#1-run-using-docker).

## Reproducible validation

Run the isolated compatibility workflow separately from the normal test suite:

```bash
make compatibility-webgoat
```

The runner starts a fresh dedicated Compose project, waits for the login page
to become healthy, runs the test, and removes the container and network on
success, failure, or interruption. It refuses to reuse an already-running
compatibility project. `FAULTWEAVER_WEBGOAT_PORT` selects another loopback host
port. The test rejects non-loopback and non-HTTP target origins.

The test creates three synthetic identities through the ordinary registration
form with random in-memory credentials. Faultweaver uses an isolated temporary
SQLite database. No credentials, session identifiers, raw HAR files, database
files, or browser screenshots are committed. Test databases retain sensitive
replay material until their temporary test directory is removed.

## Compatibility matrix

| Capability | Result | Observed validation |
| --- | --- | --- |
| Baseline crawler | Partially validated | `RUN-001` completed from `/WebGoat/login` with an eight-request ceiling and exact path scope. Requests stayed anonymous, GET-only, and body-free; no discovered form was submitted. |
| HTML form discovery | Validated | Login and registration POST forms were discovered, including username/password field metadata. |
| HAR import | Validated | The automated five-transaction capture imported 5/5 request/response pairs. A separate Google Chrome capture imported 74/74 records with zero skips; seven binary response bodies were omitted with explicit warnings. |
| cURL GET | Validated | A cookie-authenticated lesson-menu GET previewed and imported as `IMP-002` without execution. |
| cURL POST | Validated | A URL-encoded login POST previewed and imported as `IMP-003` without execution. |
| URL-encoded bodies | Validated | Registration and login bodies remained parseable; `password` and `matchingPassword` values were redacted. |
| Cookies/session state | Validated | Synthetic `JSESSIONID` cookies supported normal replay through separate Identity contexts and were redacted from operator-safe output. |
| Request Explorer | Validated | Crawler, HAR, cURL, and replay transactions retained method, path, status, provenance, redirects, and redacted request material. Browser filtering and request details worked. |
| Attack Surface | Validated | The lesson-menu endpoint retained combined HAR/cURL provenance and was available in the real UI. |
| Replay | Validated | A selected synthetic Identity replayed the shared lesson-menu GET and received JSON/200. |
| Response comparison | Validated | Authenticated JSON and anonymous redirected HTML both ended with status 200. Normalization distinguished the bodies, recorded changed redirects, and produced similarity below 0.95. |
| Authorization matrix | Validated | User-a, user-b, and Anonymous cells retained their observed 200 responses and replay links. Status alone was not treated as proof of equivalent access. |
| Candidate workflow | Validated | The identity comparison produced no automatic authorization Candidate. A passive missing-CSP Candidate was reviewed, accepted, and promoted using existing conservative behavior. |
| Finding | Validated | The accepted observation became low-severity `FW-001` with operator-authored impact, reproduction, remediation, affected endpoint, and reference. |
| Evidence | Validated | The response comparison and source response became immutable redacted `EV-001` and `EV-002` snapshots. |
| Restart persistence | Validated | A new API instance reopened the same SQLite database and recovered the completed run, imports, comparison, finding, and unchanged evidence snapshot. |
| Responsive browser behavior | Validated | Six workspace views opened in Chrome; Request Explorer filtering and details were checked visually at 1440x1000, 1024x900, 768x900, and 375x812 with zero document or request-pane horizontal overflow. |
| Retest | Not applicable | The stock target was not changed to manufacture a fixed state; the normal suite covers the retest subsystem. |
| Attack Chains | Not exercised | One confirmed passive finding did not provide a meaningful multi-finding chain. |
| OpenAPI import | Not exercised | No WebGoat API contract was supplied or inferred for this workflow. |
| WebGoat lessons and WebWolf | Not exercised | Validation used ordinary registration, session, start-page, and lesson-menu traffic only. |

## Real workflow

1. Start the pinned image on loopback and read the login and registration pages.
2. Register synthetic users normally and acquire independent session cookies.
3. Capture registration, start-page, and authenticated lesson-menu responses;
   preview and import those real transactions as HAR.
4. Import representative cURL GET and URL-encoded POST commands, then inspect
   Request Explorer and Attack Surface provenance.
5. Run a bounded anonymous baseline and inspect form metadata without
   submitting the discovered forms.
6. Replay the shared menu using a synthetic Identity, compare authenticated
   and anonymous responses, and inspect the Authorization Matrix.
7. Preserve comparison evidence, review and promote the passive missing-CSP
   observation, attach its response evidence, and reopen the API/database.
8. Independently capture normal browser activity, import its HAR, and inspect
   Requests, Attack Surface, Authorization Matrix, Candidates, Findings, and
   Evidence in the real Faultweaver UI.

No lesson vulnerability, credential attack, cross-user private data access,
destructive modification, or non-loopback target traffic was exercised.

## Browser and redaction results

The independent browser import is `IMP-004`: 74 records, 74 response records,
zero skips, and seven explicit binary-body omission warnings. Importing a
response record does not mean its binary payload was retained.

Faultweaver produced no console errors, page errors, failed requests, or HTTP
error responses during the walkthrough. The stock WebGoat page separately
emitted `Cannot read properties of undefined (reading 'ui')` and a console
resource-404 message. Registration, authenticated menu retrieval, capture,
and import still completed; no claim is made that WebGoat's browser runtime
was error-free. The 404 message was not associated with an HTTP error response
in the captured page response events.

Passwords, compound password fields, and session cookies were absent from
operator-safe previews, stored request views, identities, comparisons,
findings, evidence, and restart-persisted API output. This milestone fixed a
generic redaction gap by recognizing camel-case password components such as
`matchingPassword` and `passwordConfirmation`. Regression tests also ensure
non-secret keys such as `authorizationMatrix` and `tokenType` are not
over-redacted. No WebGoat-specific production logic or relaxed Candidate,
scope, or crawler rules were added.

## Regression validation

The final validation passed 79 backend tests, five demo tests, 15 frontend
tests, and one compatibility workflow each for Juice Shop, DVWA, and WebGoat.
Ruff lint/format checks covered 106 Python files; Svelte reported zero errors
and warnings. Frontend production output and API/web/demo Docker images built
successfully, and npm audit reported zero vulnerabilities. Locked dependency
installation did not change dependency manifests.

Existing Starlette/SQLite deprecation warnings remain. Host Node 25 is outside
Vitest's declared engine range; the frontend tests passed and the production
Docker build uses Node 22.

## Known limitations

- Crawling remains anonymous, bounded, and non-JavaScript. It does not sign in,
  submit forms, or enumerate authenticated lessons automatically.
- A lesson-menu comparison validates representation and session handling, not
  isolation of user-owned resources or an authorization vulnerability.
- cURL POST parsing/import is covered; the explicit replay assertion uses GET.
  Normal registration POSTs are performed by the HTTP/browser clients.
- The automated HAR is assembled from real HTTP responses. The independent
  browser capture and responsive walkthrough are separate manual validation,
  not ordinary CI.
- Replay credentials and captured traffic remain unencrypted at rest in local
  SQLite. Raw captures and temporary test databases must be treated as sensitive.
- Results apply to WebGoat 2026.4 at the pinned digest and the documented
  workflows. Separate [Mutillidae II validation](mutillidae.md) has its own
  bounded coverage matrix.
