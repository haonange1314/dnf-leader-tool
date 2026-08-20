# Project Instructions

## Project status

- The project targets the DNF China PC client and is currently at the end of phase 4.2.
- Phases 0 through 4 are implemented: project baseline, dungeon/personnel management, schedule foundations, CP-SAT generation, manual editing, publication, sharing, and exports.
- Phase 5 is not implemented yet. It covers multi-account authorization, a single-editor lease, production security and rate limiting, auditability, HTTPS deployment, backup/restore drills, and end-to-end/performance acceptance.
- Existing editor locks are participant, slot, and wave constraints used by manual editing and regeneration. Do not describe them as a multi-user editor lease.

## Required reading

- Read `README.md`, `docs/design.md`, `docs/technical-design.md`, `.gitignore`, and this file before making architectural or phase-level changes.
- Treat `docs/design.md` as the product scope and `docs/technical-design.md` as the implementation contract. Keep their five-phase numbering consistent with `README.md`.

## Architecture constraints

- Keep the application a modular monolith: React/TypeScript/Vite/Ant Design in `frontend`, and FastAPI/Pydantic/SQLAlchemy/Alembic in `backend`.
- Keep solver code independent from HTTP and ORM layers. Pass explicit solver input/output models into OR-Tools CP-SAT.
- Do not hard-code three teams or four members. Dungeon versions define wave, team, slot, composition, strength-order, and special-role rules.
- Published dungeon and schedule versions are immutable snapshots. New rules or personnel changes must not alter historical schedules or exports.
- Preserve both invariants: a character appears at most once per schedule, and one player contributes at most one character per wave.
- Use decimal-compatible values for damage and buffer scores; do not silently replace persisted scoring rules with frontend calculations.

## Working rules

- Preserve user changes and inspect `git status` before editing. Do not overwrite unrelated work.
- Use Alembic for schema changes and include migrations in the same change.
- Update README and design documents when behavior, commands, dependencies, phase status, or deployment assumptions change.
- Do not commit generated exports, uploads, backups, local environment files, caches, or build output.
- Local development credentials may be shown only when `VITE_SHOW_DEV_LOGIN=true`; production configuration must disable them and replace all example secrets.

## Verification

- Backend changes: run Ruff, Mypy, and relevant pytest tests from `backend`.
- Frontend changes: run TypeScript type checking, Vitest, and a production build.
- Database, API contract, publication, export, auth, proxy, or container changes: additionally run `make test-stack`.
- `make check` is the full repository acceptance command. The current test stack uses pytest, Vitest, and an isolated Docker/PostgreSQL smoke workflow; a formal Playwright E2E suite is phase 5 work.
- Keep the default 12-person raid and the custom single-team 4-person dungeon covered so generic solver/export behavior remains verified.

## Git commit conventions

- Commit messages must use the format `<type>(<scope>): <描述>`.
- Write the description in concise Chinese and summarize the actual change being committed.
- Choose `scope` from the primary responsibility of the current change. Do not mechanically reuse a fixed scope such as `schedule`.
- Prefer a specific module or capability name when it is clearer, for example: `editor`, `publication`, `solver`, `roster`, `login`, `leader`, `backend`, `frontend`, or `ci`.
- Before committing, review the staged diff and make sure both `type` and `scope` accurately describe that diff.

Common `type` values:

- `feat`: new functionality
- `fix`: bug fixes
- `docs`: documentation or comment-only changes
- `refactor`: code restructuring without behavior changes
- `style`: formatting, whitespace, or naming-only changes
- `test`: test additions or adjustments
- `chore`: dependencies, build tooling, scripts, or repository maintenance

Examples:

- `feat(editor): 完成排表编辑、版本发布与分享`
- `fix(publication): 修复历史版本恢复冲突`
- `feat(login): 在开发登录页展示测试账号`
- `test(solver): 补充自定义副本约束测试`
