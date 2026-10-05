#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
compose_file="$repository_root/compatibility/mutillidae/compose.yaml"
compose_project="faultweaver-mutillidae-compat"
mutillidae_port="${FAULTWEAVER_MUTILLIDAE_PORT:-4380}"
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
  echo "Mutillidae compatibility project is already running; stop it before using the one-shot runner" >&2
  exit 1
fi
if [ -n "$(compose ps --all --quiet)" ]; then
  compose down --volumes --remove-orphans
fi

started_by_runner=1
compose up --detach --wait
cd "$repository_root"
FAULTWEAVER_MUTILLIDAE_URL="http://127.0.0.1:$mutillidae_port" \
  uv run --project backend python -m pytest -q compatibility/mutillidae
