#!/bin/sh
set -eu

project_name="dnf-leader-tool-test-$$"
backup_file=""
invalid_backup_file=""

compose() {
    docker compose \
        --project-name "$project_name" \
        --file compose.yaml \
        --file compose.test.yaml \
        "$@"
}

cleanup() {
    if [ -n "$backup_file" ]; then
        rm -f "$backup_file"
    fi
    if [ -n "$invalid_backup_file" ]; then
        rm -f "$invalid_backup_file"
    fi
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

compose up --build --detach --wait
compose exec -T api .venv/bin/alembic check

seed_output="$(compose exec -T api .venv/bin/python -m app.cli seed)"
case "$seed_output" in
    *"BUILTIN_RAID_12: exists"*) ;;
    *)
        echo "unexpected second seed result: $seed_output" >&2
        exit 1
        ;;
esac

database_state="$(
    compose exec -T db sh -c \
        'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
        SELECT version_num
            || (SELECT '\''|'\'' || count(*) FROM dungeons)
            || (SELECT '\''|'\'' || count(*) FROM dungeon_versions)
            || (SELECT '\''|'\'' || count(*) FROM dungeon_team_templates)
            || (SELECT '\''|'\'' || sum(member_count) FROM dungeon_team_templates)
        FROM alembic_version;
        "'
)"

if [ "$database_state" != "20260901_0012|1|1|3|12" ]; then
    echo "unexpected database state: $database_state" >&2
    exit 1
fi

proxy_response="$(compose exec -T web wget -qO- http://127.0.0.1/api/v1/health/ready)"
case "$proxy_response" in
    *'"status":"ok"'*) ;;
    *)
        echo "unexpected proxy health response: $proxy_response" >&2
        exit 1
        ;;
esac

compose exec -T api .venv/bin/python tests/stack_smoke.py

if compose exec -T db psql -v ON_ERROR_STOP=1 -U dnf -d dnf_leader \
    -c "UPDATE dungeon_versions SET default_wave_count = 11 WHERE status = 'PUBLISHED'" \
    >/dev/null 2>&1; then
    echo "published dungeon version unexpectedly allowed mutation" >&2
    exit 1
fi

if compose exec -T db psql -v ON_ERROR_STOP=1 -U dnf -d dnf_leader \
    -c "UPDATE schedule_versions SET snapshot_hash = repeat('0', 64)" \
    >/dev/null 2>&1; then
    echo "published schedule version unexpectedly allowed mutation" >&2
    exit 1
fi

backup_file="$(mktemp)"
compose exec -T db sh -c \
    'pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    >"$backup_file"
test -s "$backup_file"
compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" dnf_restore_check'
compose exec -T db sh -c \
    'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d dnf_restore_check' \
    <"$backup_file"
source_state="$(
    compose exec -T db psql -At -U dnf -d dnf_leader -c \
        "SELECT (SELECT count(*) FROM users) || '|' || (SELECT count(*) FROM schedules) || '|' || (SELECT count(*) FROM schedule_versions);"
)"
restored_state="$(
    compose exec -T db psql -At -U dnf -d dnf_restore_check -c \
        "SELECT (SELECT count(*) FROM users) || '|' || (SELECT count(*) FROM schedules) || '|' || (SELECT count(*) FROM schedule_versions);"
)"
if [ "$source_state" != "$restored_state" ]; then
    echo "restored database state differs: source=$source_state restored=$restored_state" >&2
    exit 1
fi
compose exec -T db sh -c 'dropdb --force -U "$POSTGRES_USER" dnf_restore_check'

COMPOSE_PROJECT_NAME="$project_name" \
COMPOSE_OVERRIDE_FILE=compose.test.yaml \
ENV_FILE=.env.example \
CONFIRM_RESTORE=dnf_leader \
    sh scripts/restore-db.sh "$backup_file"

invalid_backup_file="$(mktemp)"
printf 'not-a-postgresql-backup\n' >"$invalid_backup_file"
if COMPOSE_PROJECT_NAME="$project_name" \
    COMPOSE_OVERRIDE_FILE=compose.test.yaml \
    ENV_FILE=.env.example \
    CONFIRM_RESTORE=dnf_leader \
        sh scripts/restore-db.sh "$invalid_backup_file" >/dev/null 2>&1; then
    echo "invalid backup unexpectedly passed restore preflight" >&2
    exit 1
fi
compose exec -T api .venv/bin/python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready')"

echo "isolated stack check passed: migration, security, edit leases, publication, exports, proxy and backup restore"
