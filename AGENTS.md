# Repository Guidelines

## Project Structure & Module Organization
Claimscope is split into focused workspaces. `apps/web` hosts the Next.js 14 front end (App Router) while `apps/api` contains the FastAPI service and the `worker/` queue runner. Shared TypeScript types live in `packages/shared`; adapter stubs for external evaluation harnesses live under `packages/harness`. Operational assets are grouped in `infra/` (IaC & Docker templates), `evals/` (nightly collections), `demo/` (seeded receipts and artifacts), `docs/` (method cards), and `scripts/` (maintenance helpers).

## Build, Test, and Development Commands
Clone the repo, copy `.env.example` to `.env`, then run `docker compose up --build` to start the full stack. For focused work: `cd apps/web && npm install && npm run dev` launches the web client on port 3000; `npm run lint` runs `next lint`. Back-end work happens in `apps/api`: `pip install -r requirements.txt` followed by `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` spins up the API, and `python -m worker.main` processes queued runs against the local Postgres/Redis/MinIO services.

## Coding Style & Naming Conventions
TypeScript/TSX follows the existing two-space indentation, double quotes, and strict typing enforced by `tsconfig.json`. Co-locate route handlers and components in `app/` folders, exporting default client components where interactive state is required. Python modules use four-space indents, `snake_case` identifiers, and FastAPI/Pydantic type hints; prefer early returns and small helper functions (see `apps/api/app/main.py`). Keep shared constants in `packages/shared` rather than duplicating literals.

## Testing Guidelines
Automated coverage is light today, so new work should add tests alongside code. For the API, create `pytest` suites under `apps/api/tests` using FastAPI's `TestClient` and seed the database with transaction-scoped fixtures. Front-end behaviour should be validated with `@testing-library/react` co-located in `__tests__` directories. When touching evaluation runners, add deterministic sample cases (seeded random streams) and verify end-to-end by submitting the `demo` presets through the local stack.

## Commit & Pull Request Guidelines
Upstream history uses short, imperative commit subjects (e.g., `Add seeded receipts demo`, `Fix worker bootstrap tracking`); keep the first line ≤72 characters and include an optional wrapped body explaining _what_ and _why_. For pull requests, link related issues, note any schema or migration changes, paste test or repro command output, and include screenshots or receipts for UI-affecting work. Use draft PRs while iterating and request review only after lint/tests are green.

## Environment & Secrets
Never commit real provider keys. Reference logical IDs (e.g., `ANTHROPIC_API_KEY_REF`) in code and load actual secrets via your runner or local `.env`. If you rotate storage endpoints, update both the service configs and the seeded artifacts in `demo/` to keep tutorials functional.
