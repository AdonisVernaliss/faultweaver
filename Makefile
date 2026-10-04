.PHONY: backend-install backend-test backend-lint demo-lint demo-test frontend-install frontend-check frontend-test frontend-build

backend-install:
	uv sync --project backend --all-groups

backend-test:
	uv run --project backend pytest -q

backend-lint:
	uv run --project backend ruff check .
	uv run --project backend ruff format --check .

demo-lint:
	uv run --project backend ruff check --config backend/pyproject.toml demo
	uv run --project backend ruff format --check --config backend/pyproject.toml demo

demo-test:
	uv run --project backend python -m pytest -q demo/tests

frontend-install:
	npm ci --prefix frontend

frontend-check:
	npm run check --prefix frontend

frontend-test:
	npm test --prefix frontend

frontend-build:
	npm run build --prefix frontend
