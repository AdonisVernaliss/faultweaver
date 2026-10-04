#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
compose_file="$repository_root/compatibility/juice-shop/compose.yaml"
compose_project="faultweaver-juice-shop-compat"
juice_shop_port="${FAULTWEAVER_JUICE_SHOP_PORT:-3008}"
started_by_runner=0

compose() {
  docker compose --project-name "$compose_project" --file "$compose_file" "$@"
}

cleanup() {
  if [ "$started_by_runner" -eq 1 ]; then
    compose down --remove-orphans
  fi
}

trap cleanup EXIT HUP INT TERM

if [ -z "$(compose ps --status running --quiet juice-shop)" ]; then
  started_by_runner=1
  compose up --detach --wait juice-shop
fi

cd "$repository_root"
FAULTWEAVER_JUICE_SHOP_URL="http://127.0.0.1:$juice_shop_port" \
  uv run --project backend python -m pytest -q compatibility/juice-shop
