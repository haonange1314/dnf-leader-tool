#!/bin/sh
set -eu

project_name="dnf-leader-tool-test-$$"

compose() {
    docker compose \
        --project-name "$project_name" \
        --file compose.yaml \
        --file compose.test.yaml \
        "$@"
}

cleanup() {
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

if [ "$database_state" != "20260818_0001|1|1|3|12" ]; then
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

echo "isolated stack check passed: migration, seed, database schema, health and proxy"
