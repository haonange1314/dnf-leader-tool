#!/bin/sh
set -eu

project_name="dnf-leader-tool-e2e-$$"

compose() {
    docker compose \
        --project-name "$project_name" \
        --file compose.yaml \
        --file compose.e2e.yaml \
        "$@"
}

cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

compose up --build --detach --wait
E2E_BASE_URL=http://127.0.0.1:15173 pnpm --filter @dnf-leader/frontend test:e2e
