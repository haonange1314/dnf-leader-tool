#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: CONFIRM_RESTORE=dnf_leader $0 <backup.dump>" >&2
    exit 1
fi

backup_file="$1"
env_file="${ENV_FILE:-.env.production}"
compose_override_file="${COMPOSE_OVERRIDE_FILE:-compose.production.yaml}"

if [ ! -f "$backup_file" ] || [ ! -s "$backup_file" ]; then
    echo "backup file is missing or empty: $backup_file" >&2
    exit 1
fi
if [ ! -f "$env_file" ]; then
    echo "production env file not found: $env_file" >&2
    exit 1
fi
if [ ! -f "$compose_override_file" ]; then
    echo "compose override file not found: $compose_override_file" >&2
    exit 1
fi
if [ "${CONFIRM_RESTORE:-}" != "dnf_leader" ]; then
    echo "restore replaces the production database; set CONFIRM_RESTORE=dnf_leader" >&2
    exit 1
fi

compose() {
    docker compose --env-file "$env_file" -f compose.yaml -f "$compose_override_file" "$@"
}

restore_suffix="$(date -u +%Y%m%dT%H%M%SZ)_$$"
restore_db="dnf_restore_$restore_suffix"
previous_db="dnf_previous_$restore_suffix"
api_stopped=0
swapped=0
completed=0

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$completed" -eq 0 ]; then
        if [ "$swapped" -eq 0 ]; then
            compose exec -T -e RESTORE_DB="$restore_db" db sh -c \
                'dropdb --if-exists --force -U "$POSTGRES_USER" "$RESTORE_DB"' \
                >/dev/null 2>&1 || true
        fi
        if [ "$api_stopped" -eq 1 ]; then
            compose stop api >/dev/null 2>&1 || true
            echo "restore did not complete; API remains stopped and the previous database is preserved as $previous_db" >&2
        fi
    fi
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

# Reject truncated or non-PostgreSQL archives before touching any database.
compose exec -T db sh -c 'pg_restore --list >/dev/null' <"$backup_file"

# Restore and inspect an isolated database while the current API remains available.
compose exec -T -e RESTORE_DB="$restore_db" db sh -c \
    'dropdb --if-exists --force -U "$POSTGRES_USER" "$RESTORE_DB" && createdb -U "$POSTGRES_USER" "$RESTORE_DB"'
compose exec -T -e RESTORE_DB="$restore_db" db sh -c \
    'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$RESTORE_DB"' \
    <"$backup_file"
compose exec -T -e RESTORE_DB="$restore_db" db sh -c \
    'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$RESTORE_DB" -c "SELECT version_num FROM alembic_version" >/dev/null'

compose stop api
api_stopped=1

# Keep the previous production database until the restored application passes health checks.
compose exec -T \
    -e RESTORE_DB="$restore_db" \
    -e PREVIOUS_DB="$previous_db" \
    db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v target="$POSTGRES_DB" -v replacement="$RESTORE_DB" -v previous="$PREVIOUS_DB"' <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'target' AND pid <> pg_backend_pid();
SELECT format('ALTER DATABASE %I RENAME TO %I', :'target', :'previous') \gexec
SELECT format('ALTER DATABASE %I RENAME TO %I', :'replacement', :'target') \gexec
SQL
swapped=1

compose up --detach --wait api
compose exec -T api .venv/bin/alembic current
compose exec -T api .venv/bin/python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready')"
api_stopped=0

compose exec -T -e PREVIOUS_DB="$previous_db" db sh -c \
    'dropdb --if-exists --force -U "$POSTGRES_USER" "$PREVIOUS_DB"'

completed=1
trap - EXIT HUP INT TERM
echo "database restore completed from $backup_file"
