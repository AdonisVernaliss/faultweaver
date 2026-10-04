.PHONY: backend-install backend-test backend-lint demo-lint demo-test frontend-install frontend-check frontend-test frontend-build compatibility-juice-shop compatibility-juice-shop-up compatibility-juice-shop-test compatibility-juice-shop-down

backend-install:
	uv sync --project backend --all-groups

backend-test:
	uv run --project backend python -m pytest -q backend/tests

backend-lint:
	uv run --project backend ruff check backend
	uv run --project backend ruff format --check backend

demo-lint:
	uv run --project backend ruff check demo
	uv run --project backend ruff format --check demo

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

compatibility-juice-shop:
	./compatibility/juice-shop/run.sh

compatibility-juice-shop-up:
	docker compose --project-name faultweaver-juice-shop-compat --file compatibility/juice-shop/compose.yaml up --detach --wait juice-shop

compatibility-juice-shop-test:
	FAULTWEAVER_JUICE_SHOP_URL=$${FAULTWEAVER_JUICE_SHOP_URL:-http://127.0.0.1:3008} uv run --project backend python -m pytest -q compatibility/juice-shop

compatibility-juice-shop-down:
	docker compose --project-name faultweaver-juice-shop-compat --file compatibility/juice-shop/compose.yaml down --remove-orphans
