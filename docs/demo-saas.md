# Deliberately vulnerable demo SaaS

Northstar Billing is a deterministic local target for validating Faultweaver's
existing workflow. It is intentionally insecure and must never be exposed to an
untrusted network. It is not a compatibility claim for any third-party lab.

## Safety boundary

- The service is opt-in through the Compose `demo` profile.
- Docker publishes it only on `127.0.0.1:8088`.
- The container is read-only, runs as `nobody`, drops all Linux capabilities,
  and enables `no-new-privileges`.
- The application has no outbound HTTP client, database, file upload, command
  execution, template evaluation, or mutable business data.
- Host-native execution defaults to `127.0.0.1`; a non-loopback bind is rejected
  unless an explicit override is present.
- All credentials and records are public synthetic fixtures.

## Synthetic identities

| Identity | Browser login | Bearer token | Intended role |
| --- | --- | --- | --- |
| Alice | `alice / demo-alice` | `demo-alice-token` | Tenant member |
| Bob | `bob / demo-bob` | `demo-bob-token` | Tenant member |
| Administrator | `admin / demo-admin` | `demo-admin-token` | Administrator |

## Deliberate defects

### Horizontal object authorization

`GET /api/invoices/1001` and `GET /api/invoices/2002` authenticate a caller but
deliberately omit the ownership check. The collection endpoint
`GET /api/invoices` is the control: it returns only the caller's own invoice.

Expected Faultweaver path:

1. Let the baseline assessment record the anonymous 401 response for
   `/api/invoices/1001`.
2. Create Alice and Bob bearer identities.
3. Compare the recorded request across those identities.
4. Both replays return the same successful object response, producing a
   conservative authorization Candidate for manual verification.

### Administrator function authorization

`GET /api/admin/audit/2026` deliberately checks authentication without checking
the caller's role. Compare the request using an administrator identity and a
tenant identity; both receive the same successful audit response.

## Passive baseline fixtures

The anonymous crawl also encounters:

- HTML without CSP, X-Content-Type-Options, or HSTS;
- a `session` cookie without `HttpOnly`;
- a plain-HTTP password form that the crawler records but does not submit;
- `/api/public-config`, whose JSON contains a sensitive-looking field name but
  only a synthetic placeholder value;
- `/debug/error`, a deterministic 500 response containing a stack-trace and
  internal-path marker;
- an external loopback-port link that must be recorded as out of scope and never
  requested;
- stylesheet metadata that must not be fetched by the crawler.

## Compose workflow

```bash
docker compose --profile demo up --build
```

Use `http://demo:8088/` as both the exact scope origin and assessment target when
Faultweaver itself runs in Compose. Use `http://127.0.0.1:8088/` only when the
backend runs directly on the host. The direct browser view is always
`http://127.0.0.1:8088/`.

After the baseline completes, inspect crawler provenance in Request Explorer
and Attack Surface, compare the numbered invoice or audit request with the
synthetic identities, review the Candidate and supporting replay evidence, and
promote it only after explicit manual verification.
