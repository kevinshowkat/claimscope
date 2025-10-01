# Claimscope — Labs Edition

Claimscope ingests AI-lab evaluation claims, reproduces them with pinned, open harnesses, and publishes a shareable receipt per claim with a neutral status: Replicated / Setting Drift / Underspecified / Not Reproduced.

## One-command local repro

```bash
git clone https://github.com/claimscope/claimscope
cd claimscope
cp .env.example .env  # update provider key refs if needed
docker compose up --build
# open http://localhost:3000
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

## Telemetry
Set `ANALYTICS_DISABLED=true` to opt-out.
