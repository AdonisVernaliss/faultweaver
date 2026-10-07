# Getting started

Start the local workspace using the [Docker Quick Start](../README.md#quick-start).
Faultweaver is for one trusted operator assessing systems they own or are
explicitly authorized to test. Do not expose the workspace or vulnerable demo
to a shared network or the internet.

## First assessment

1. Create an **Engagement** and add exact authorized scope: scheme, hostname,
   port, and path prefix. Discovery never expands authorization.
2. Open **Assessments → New Baseline**, enter an in-scope URL, and review the
   page, depth, request, rate, and timeout limits before starting. The crawler
   sends only anonymous GET requests.
3. Review Discovered Surface, Requests, Observations, Candidates, and Warnings.
   Stop preserves partial work; a process restart marks interrupted runs Stopped
   rather than resuming traffic automatically.
4. Choose **Import Traffic** to preview raw HTTP, HAR, cURL, or OpenAPI data.
   Review the redacted summary before importing. No traffic is sent by import.
5. Inspect observed and declared endpoints in **Attack Surface**, then use
   **Requests** to search and inspect individual transactions.
6. Select **Replay** only when you intend to send the request. Add explicit
   **Identity** contexts for authorized credentials and use **Compare identities**
   where relevant. Review saved results in **Auth matrix**; untested cells are
   not authorization decisions.
7. Verify a **Candidate** manually before promotion. Write the Finding's impact,
   reproduction steps, and remediation; automated reasoning is not copied into
   the final prose.
8. Preserve redacted request, replay, comparison, or note **Evidence**. Snapshots
   are immutable even if their source changes later.
9. If confirmed issues form a meaningful path, author an **Attack Chain** with
   ordered Finding/intermediate steps, Evidence links, and resulting impact.
   Validation records the operator's review; it does not execute the chain.
10. Record **Retests** separately with their outcome and Evidence. Do not overwrite
    original verification records or imply a fix that has not been observed.
11. Open **Report**, author conclusions and limitations, review the selected
    Findings/chains, and preserve a revision. Download HTML, Markdown, or JSON
    from that revision. Treat every export as confidential plaintext.

For a synthetic practice assessment, use the optional
[Northstar Billing demo](demo-saas.md). When the backend runs in Compose, its
target address is `http://demo:8088/`, not the host browser's loopback address.

## Import boundaries

- **Raw HTTP** accepts a request line, headers, and optional body relative to a
  supplied base URL.
- **HAR 1.2** retains transactions, duplicate headers, timings, redirects, and
  textual or valid UTF-8 base64 bodies. Malformed entries are reported separately;
  binary bodies are represented as omitted.
- **cURL** parses a common browser-copy subset, including method, headers,
  cookies, data, JSON, GET query data, quoting, and multiline input. Commands are
  never executed. File reads, shell expansion, and execution/network-control
  options are rejected or warned about.
- **OpenAPI 3.0/3.1** accepts JSON or safe YAML. Supported internal references
  are resolved; external references remain warnings and are never fetched.
  Declared servers are not contacted, and schemas do not generate requests.

Defaults are 10 MB per document, 5,000 records, and 1 MB per captured request or
response body. Concrete observed paths are not guessed into templates; a matching
OpenAPI declaration must supply that evidence. See [architecture](architecture.md).

## Native development

Use Python 3.13, `uv`, and Node.js 22.x (22.17 or later). The repository's
`.python-version` and frontend `.nvmrc` declare the tested major versions.

```bash
make install
```

For a fresh installation using the native OS key store, with no file-provider
environment overrides configured:

```bash
uv run --project backend faultweaver-storage init-key
```

Then run the API and frontend in separate terminals:

```bash
uv run --project backend uvicorn faultweaver.app:app --reload
```

```bash
npm run dev --prefix frontend
```

Open http://localhost:5173. The frontend proxies `/api` to
http://localhost:8000. Encrypted native state is stored in `data/faultweaver.db`;
it is separate from the Compose volume. Startup never creates a missing key or
silently opens a legacy plaintext database. See
[key providers and migration](secret-storage.md) before changing storage mode.

Run all normal validation with `make validate`, or focused checks:

```bash
make backend-lint backend-test
make demo-lint demo-test
make frontend-check frontend-test frontend-build
```

Compatibility labs are intentionally vulnerable external applications and remain
opt-in. Their matrices describe exact versions, local isolation, commands, and
coverage limits; they are not part of normal CI.
