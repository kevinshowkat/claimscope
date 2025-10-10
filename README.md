# Eval Receipts — Labs Edition

Eval Receipts ingests AI-lab evaluation claims, reproduces them with pinned, open harnesses, and publishes a shareable receipt per claim with a neutral status: Replicated / Setting Drift / Underspecified / Not Reproduced.

## One-command local repro

```bash
git clone https://github.com/kevinshowkat/eval-receipts
cd eval-receipts
cp .env.example .env  # update provider key refs if needed
docker compose up --build
# open http://localhost:3000

# after changing API/worker code, rebuild running containers
docker compose build api worker
docker compose up -d api worker

# optional: hot reload UI locally
docker compose stop web
cd apps/web && npm install && npm run dev
# open http://localhost:3000 in another tab

# re-enable containerized web build when finished
docker compose up -d web
```

## Structure

- apps/web — Next.js 14 (App Router)
- apps/api — FastAPI service + workers
- packages/harness — adapters (lm-eval, swe-bench, cAgent, cGUI)
- packages/shared — types/schemas/utils
- infra — IaC & Docker
- evals — nightly collections & canaries
- docs — method/dataset cards
- demo — seeded claims and artifacts

## API (stubbed)

FastAPI exposes:
- POST /submit_claim — ingest text or URL, returns parsed claim IDs
- POST /run_reproduction — enqueue a reproduction run
- GET /runs/{run_id} — run status & outputs
- GET /claims/{claim_id} — claim + run summaries

OpenAPI stub lives at `apps/api/openapi.yaml`.

## Licenses
- App: MIT (root LICENSE)
- Harness adapters: Apache-2.0 (`packages/harness/LICENSE-APACHE`)

## CI
GitHub Actions builds web and sanity-checks API. PR previews can be enabled with Vercel + Railway/Fly.io.

## Harness suites
- Coding & reasoning harnesses call Anthropic APIs; set `ANTHROPIC_API_KEY` and keep `budget_usd >= 0.02` when invoking `/run_reproduction`.
- Agents (`cAgent-12`) is fully offline and deterministic. Workers load YAML tasks from `packages/harness/cagent/tasks` and emit an `agent_trace.json` artifact per run.
- GUI (`cGUI-10`) relies on Playwright headless runs hitting `/cgui` routes in the Next.js app. Install Node 20 and run `npm install` inside `packages/harness/cgui`, then `npx playwright test --config packages/harness/cgui/playwright.config.ts` with the web app running locally, or leverage the new runner with `docker compose run --rm gui bash -lc "cd packages/harness/cgui && npm install && npx playwright test --config playwright.config.ts"`. The production Next.js bundle also exposes the new claim validator UI that visualises each sentence-level claim, runs the appropriate harness, and surfaces metrics/artifacts in a lay person-friendly summary.
- Every harness writes a trace manifest into the `traces` table summarising dataset hashes, seeds, and runtime metadata. See `docs/TRACE_MANIFEST.md` for inspection tips.
- To smoke-test agents locally, run `PYTHONPATH=. python3 -m pytest apps/api/tests/test_agents_cagent.py` or use `python3 -m apps.api.worker.agents_cagent` once a CLI entrypoint is added.

## Telemetry
Set `ANALYTICS_DISABLED=true` to opt-out.
