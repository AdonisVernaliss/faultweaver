#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
compose_file="$repository_root/compatibility/webgoat/compose.yaml"
compose_project="faultweaver-webgoat-compat"
webgoat_port="${FAULTWEAVER_WEBGOAT_PORT:-4080}"
started_by_runner=0

compose() {
  docker compose --project-name "$compose_project" --file "$compose_file" "$@"
}

cleanup() {
  if [ "$started_by_runner" -eq 1 ]; then
    compose down --volumes --remove-orphans
  fi
}

trap cleanup EXIT HUP INT TERM

if [ -n "$(compose ps --status running --quiet)" ]; then
  echo "WebGoat compatibility project is already running; stop it before using the one-shot runner" >&2
  exit 1
fi
if [ -n "$(compose ps --all --quiet)" ]; then
  compose down --volumes --remove-orphans
fi

started_by_runner=1
compose up --detach --wait

cd "$repository_root"
FAULTWEAVER_WEBGOAT_URL="http://127.0.0.1:$webgoat_port" \
  uv run --project backend python -m pytest -q compatibility/webgoat
