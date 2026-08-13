# Contributing

Use `feature/*`, `fix/*`, or `chore/*` branches and open a pull request into `main`; `main` must remain deployable. Keep commits focused and explain why architectural or dependency changes are necessary.

Before opening a PR run `make lint`, `make typecheck`, and `make test`; for web changes also run `pnpm --filter web build`. Add or update tests with behavior. Update documentation when contracts or workflows change. Database changes require a committed Alembic migration; destructive migrations need explicit review. Never commit customer data or secrets.

PRs should describe scope, architecture impact, testing evidence, migration/rollback concerns, and security/privacy impact. Reviews reject hidden constants, analytical code in routes, unclassified causal language, and leakage across the decision-time boundary.

Agents and contributors must update `TASKS.md` when task status changes. Update `memory/CURRENT_STATE.md` only for material milestone/blocker/scope changes, add cross-role work to `memory/HANDOFFS.md`, and record deliberate durable decisions in `DECISIONS.md`. Do not use project memory as a development diary.
