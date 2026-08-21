#!/bin/sh
set -eu

env_file="${ENV_FILE:-.env.production}"
backup_dir="${BACKUP_DIR:-./backups}"

if [ ! -f "$env_file" ]; then
    echo "production env file not found: $env_file" >&2
    exit 1
fi

case "$backup_dir" in
    /|""|.)
        echo "BACKUP_DIR must be a dedicated directory, not '$backup_dir'" >&2
        exit 1
        ;;
esac

mkdir -p "$backup_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_dir/dnf-leader-$timestamp.dump"
temporary="$target.partial"

cleanup() {
    rm -f "$temporary"
}
trap cleanup EXIT INT TERM

docker compose --env-file "$env_file" -f compose.yaml -f compose.production.yaml \
    exec -T db sh -c 'pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    >"$temporary"

test -s "$temporary"
mv "$temporary" "$target"
trap - EXIT INT TERM
echo "$target"
