# Project Instructions

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
