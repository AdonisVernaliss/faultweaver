#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
compose_file="$repository_root/compatibility/dvwa/compose.yaml"
compose_project="faultweaver-dvwa-compat"
dvwa_port="${FAULTWEAVER_DVWA_PORT:-4280}"
started_by_runner=0

FAULTWEAVER_DVWA_DB_PASSWORD="$(openssl rand -hex 24)"
FAULTWEAVER_DVWA_DB_ROOT_PASSWORD="$(openssl rand -hex 24)"
FAULTWEAVER_DVWA_PASSWORD="$(openssl rand -hex 24)"
FAULTWEAVER_DVWA_USERNAME="compat-user-a"
export FAULTWEAVER_DVWA_DB_PASSWORD FAULTWEAVER_DVWA_DB_ROOT_PASSWORD
export FAULTWEAVER_DVWA_PASSWORD FAULTWEAVER_DVWA_USERNAME

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
  echo "DVWA compatibility project is already running; stop it before using the one-shot runner" >&2
  exit 1
fi
if [ -n "$(compose ps --all --quiet)" ]; then
  compose down --volumes --remove-orphans
fi

started_by_runner=1
compose up --detach --wait

cd "$repository_root"
FAULTWEAVER_DVWA_URL="http://127.0.0.1:$dvwa_port" \
  uv run --project backend python compatibility/dvwa/prepare_target.py

compose exec --no-TTY -e MYSQL_PWD="$FAULTWEAVER_DVWA_DB_PASSWORD" db \
  mariadb --user=dvwa dvwa --execute="UPDATE users SET user='$FAULTWEAVER_DVWA_USERNAME', password=MD5('$FAULTWEAVER_DVWA_PASSWORD') WHERE user_id=1"

FAULTWEAVER_DVWA_URL="http://127.0.0.1:$dvwa_port" \
  uv run --project backend python -m pytest -q compatibility/dvwa
