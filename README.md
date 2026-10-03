# Faultweaver

Faultweaver is a local-first Web/API penetration-testing engine and engagement workspace. It is designed around a deliberate workflow: discover and import HTTP traffic, perform conservative analysis, verify candidate findings manually, preserve evidence, connect confirmed issues into attack chains, retest, and report.

Faultweaver is not a promise of complete vulnerability coverage. Automated observations remain candidates until an operator verifies them.

> [!WARNING]
> Use Faultweaver only against systems you own or have explicit authorization to test.

## Current status

Faultweaver is pre-release software. The first functional vertical slice is available:

- create and reopen engagements;
- authorize exact scheme, hostname, port, and path-prefix scope rules;
- import raw HTTP requests without sending them;
- search and inspect stored traffic in a split-pane Request Explorer;
- replay a request with per-hop redirect scope checks;
- persist imported requests, replay responses, and engagement state in SQLite.

Candidate analysis, identities, differential comparison, findings, evidence, attack chains, reports, crawling, and the deterministic demo target remain later milestones.

## Architecture

- FastAPI, SQLAlchemy, and SQLite backend
- SvelteKit and TypeScript frontend
- Docker Compose for local deployment

The backend validates scheme, hostname, port, and path restrictions before outbound traffic is sent. Redirect destinations are evaluated independently.

## Development

Prerequisites: Python 3.13+, `uv`, and Node.js 22.17+.

```bash
uv sync --project backend --all-groups
npm ci --prefix frontend
```

Run the API and frontend in separate terminals:

```bash
uv run --project backend uvicorn faultweaver.app:app --reload
npm run dev --prefix frontend
```

Open `http://localhost:5173`. The frontend proxies `/api` to `http://localhost:8000` by default. Local state is stored in `data/faultweaver.db`.

Run the validated checks:

```bash
make backend-lint backend-test
make frontend-check frontend-test frontend-build
```

## Docker Compose

```bash
docker compose up --build
```

The workspace is available at `http://localhost:5173`, the API at `http://localhost:8000`, and SQLite data is retained in the `faultweaver-data` volume.

## First workflow

1. Create an engagement.
2. Add an authorized scope rule. Scope must match before import and immediately before every outbound request or redirect.
3. Import a raw request from Request Explorer.
4. Select the stored request and choose **Replay**.
5. Inspect the persisted replay response. A replay is traffic evidence, not a confirmed vulnerability.

See [Architecture](docs/architecture.md) for the current boundaries and design decisions.

## Security model

Faultweaver favors conservative request limits and explicit operator actions. It does not implement credential attacks, denial of service, persistence, destructive modification, malware deployment, shell exploitation, or stealth/evasion capabilities.

## License

MIT.
