# Faultweaver

Faultweaver is a local-first Web/API penetration-testing engine and engagement workspace. It is designed around a deliberate workflow: discover and import HTTP traffic, perform conservative analysis, verify candidate findings manually, preserve evidence, connect confirmed issues into attack chains, retest, and report.

Faultweaver is not a promise of complete vulnerability coverage. Automated observations remain candidates until an operator verifies them.

> [!WARNING]
> Use Faultweaver only against systems you own or have explicit authorization to test.

## Current status

Faultweaver is under active development. The first milestone covers engagement creation, backend-enforced target scope, raw HTTP import, a request explorer, safe replay, and SQLite persistence.

## Architecture

- FastAPI, SQLAlchemy, and SQLite backend
- SvelteKit and TypeScript frontend
- Docker Compose for local deployment

The backend validates scheme, hostname, port, and path restrictions before outbound traffic is sent. Redirect destinations are evaluated independently.

## Development

Detailed setup commands will be added once the first runnable vertical slice is validated. Python 3.13+ and a current Node.js LTS release are the intended local toolchain.

## Security model

Faultweaver favors conservative request limits and explicit operator actions. It does not implement credential attacks, denial of service, persistence, destructive modification, malware deployment, shell exploitation, or stealth/evasion capabilities.

## License

Apache-2.0.
