# Repository Guidelines

## Project Structure & Module Organization

This is a small monorepo for Shinkai, a long-running observable research agent.

- `services/api/`: FastAPI backend, agent harness, run/event stores, graph, eval, tools, and A2A endpoints.
- `apps/web/`: Next.js dashboard for runs, graph, eval, review, and A2A views.
- `packages/shared-types/` and `packages/ui/`: shared TypeScript package placeholders.
- `docs/`: architecture, agent-loop, graph, autonomous discovery, and checklist specs.
- `scripts/`: local dev and smoke-test helpers.

Runtime state is written under `.shinkai/` by default and must not be committed.

## Build, Test, and Development Commands

- `make setup`: install workspace dependencies.
- `make dev`: run API on `:8100` and web on `:3100`.
- `make api`: start only the FastAPI service.
- `make web`: start only the Next.js app.
- `make lint`: run backend ruff checks and frontend TypeScript checks.
- `make test`: run backend pytest suite.
- `make smoke`: start isolated local services and verify health, CORS, web page loading, autonomous run execution, graph output, and eval output.

Manual equivalents: `cd services/api && uv run pytest`, `cd services/api && uv run ruff check src tests`, and `pnpm --filter @shinkai/web lint`.

## Coding Style & Naming Conventions

Python targets 3.13 and uses ruff with 100-character lines. Prefer typed Pydantic models for API and state contracts. Keep agent events explicit and traceable through `AgentEvent`.

TypeScript uses strict Next.js/React conventions. Components live in `apps/web/components/portal/`; pages live in `apps/web/app/`. Use PascalCase for React components and kebab-case for Markdown docs.

## Testing Guidelines

Backend tests use pytest in `services/api/tests/`. Name tests `test_*.py` and cover lifecycle, persistence, graph, eval, and harness behavior when contracts change. Use deterministic runs with `allow_live_sources: false` for stable tests; reserve live-source checks for smoke or explicitly mocked tools.

## Commit & Pull Request Guidelines

There is no established history yet; use concise conventional prefixes such as `feat:`, `fix:`, `test:`, and `docs:`. PRs should include scope, reason, linked design docs or issues, and verification performed. UI changes should include screenshots or a smoke-test note.

## Security & Configuration

Never commit API keys. Configure DeepSeek through environment variables such as `SHINKAI_DEEPSEEK_API_KEY` and `SHINKAI_LLM_MODEL`. Keep `.env`, `.env.local`, and `.shinkai/` local only.
