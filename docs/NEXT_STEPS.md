# Remaining Work Checklist

This doc tracks the outstanding tasks after staging the cAgent-12 harness.

## 1. GUI Harness (cGUI-10)
- [x] Build deterministic mini apps under `apps/web/app/cgui/`.
- [x] Write 10 Playwright specs in `packages/harness/cgui/tests/` with trace artifacts enabled.
- [x] Implement `apps/api/worker/gui_cgui.py` to launch the suite, parse JSON output, compute metrics, and zip traces.
- [x] Extend `docker-compose.yml` with a Playwright-capable service (or document local runner) and update requirements.
- [x] Add CI job to install browsers and run a smoke spec.

## 2. Web UI Enhancements
- [x] Introduce a reusable receipt component showing score, CI bar, ops capsule, and artifact links.
- [x] Surface agent and GUI metrics (success rates, tool-error, p95 wall-clock) in Parsed Claims.
- [ ] Address hydration/state issues flagged in audit and ensure focus order/a11y remain intact.

## 3. Trace Manifest & Budget Logging
- [x] Create a helper to record dataset IDs, seeds, harness versions, and docker image hashes into the `traces` table.
- [x] Ensure every runner (coding, gsm8k, agents, gui) calls the helper with deterministic seeds.
- [x] Enforce/record budget estimates for offline suites.

## 4. Docs & Verification
- [ ] Expand README with “How to run GUI locally” instructions and artifact expectations.
- [ ] Add changelog entries/screenshots once UI updates land.
- [ ] Verify end-to-end flows via `docker compose up --build` and the curl smoke commands in the spec.

Keep this list updated as tasks complete.
