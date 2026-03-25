# Council — AI Agent Security Framework

Council is a dynamic safety layer for OpenClaw agents. Instead of static allow/deny lists, Council evaluates every proposed action for policy fit, safety risk, intent alignment, and emergent sequence harm before anything runs.

## What It Does
1. **Intercept** every tool call the agent wants to run.
2. **Pre-filter** trivial read-only and first-party actions for instant execution.
3. **Review** remaining actions through a multi-checker "Council" (policy, safety, intent, sequence).
4. **Assign a tier** (auto, notify, approval, block) with confidence-aware escalation.
5. **Record + verify** the final verdict inside a cryptographic verification chain (EigenCloud-ready) and expose it through the Insights/Activity UI.

## Key Features
- **3-checker Review Council** (policy, safety, intent) trained with AgentHarm few-shots and confidence scoring.
- **4th sequence analyzer** that spots chained malicious patterns (data exfiltration, impersonation, credential theft, sabotage, fraud).
- **Adaptive pre-filter** that learns from approvals and auto-executes repeated safe patterns.
- **Rate limiting + first-use escalation** to catch runaway loops and unfamiliar tools.
- **Prompt-injection detection** baked into the safety checker — content containing "ignore previous instructions" is auto-flagged.
- **Cryptographic verification chain** with immutable receipts + `/api/verification/*` endpoints (ready for EigenDA submission).
- **Override workflow** that logs a new receipt, updates the timeline, and unblocks Tier 4 decisions when a human insists.
- **Benchmark runner & Insights UI** powered by 100 scenarios (AgentHarm + custom tiers) with live metrics.
- **Mobile-first PWA**: Chat, Approvals, Activity timeline with override buttons, Insights dashboard, and Settings (risk profile, audit tools).

## Benchmark Results (AgentHarm + custom scenarios)
Latest run (`2026-03-24`, conservative profile, `gpt-4o-mini`):
- Harm prevention: **100%** (50 / 50 harmful scenarios stopped)
- False positive rate: **36%** (9 / 25 safe actions escalated by the new sequence guard)
- Context accuracy: **33%** (5 / 15)
- Sequence detection: **100%** (10 / 10 compositional attacks blocked)
- Overall accuracy: **81%** · Avg latency: **2137 ms** · Pre-filter hit rate: **22.5%**

Without Council: 0% protection — every harmful AgentHarm behavior succeeds. See [`BENCHMARK.md`](./BENCHMARK.md) for the full timeline (baseline → Run 1 → Run 2 → Final Run) plus pointers to the raw artifacts.

## Architecture
```
             ┌────────────────────────────────────────────────────────────┐
User Prompt →│ Primary Agent proposes tool call (tool, params, reasoning) │
             └────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                      ┌──────────────────────────────┐
                      │ Tier Pre-Filter (fast heur.) │
                      └──────────────┬───────────────┘
                                     │auto-safe
       needs review                   ▼
                                     ┌──────────────────────────────────────────────────────────────┐
                                     │ Review Council (parallel)                                    │
                                     │  • Policy checker (profile-aware)                            │
                                     │  • Safety checker (AgentHarm few-shots + prompt-injection)   │
                                     │  • Intent checker (goal alignment)                           │
                                     │  • Sequence analyzer (emergent harm patterns)                │
                                     └──────────────┬──────────────┬──────────────┬────────────────┘
                                                    │ votes + confidence
                                                    ▼
                                   ┌──────────────────────────────────────────┐
                                   │ Tier Classifier                          │
                                   │  - adaptive pre-filter learnings         │
                                   │  - confidence based escalation           │
                                   │  - rate limiting / first-use bump        │
                                   └──────────────┬──────────────┬────────────┘
                                                  ▼              ▼
                                          Tier 1/2 execute   Tier 3 queue   Tier 4 block
                                                  │              │              │
                                                  ▼              ▼              ▼
                                         Agent + Activity   Approvals UI   Override endpoint
                                                  
                                                  ▼
                                Cryptographic Verification Chain (EigenCloud-ready)
                                                  ▼
                                  Insights UI · Audit Trail · Benchmark APIs
```

## Installation
```bash
git clone https://github.com/Sanjith-Shan/Council.git ~/projects/council
cd ~/projects/council
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add OPENAI_API_KEY + OPENCLAW_GATEWAY_TOKEN
python server.py
```
Open http://localhost:8000 to load the dashboard (installable PWA).

## Deployment & Mobile PWA
- `./start.sh` boots the FastAPI server on port 8001 with logging.
- Expose it with ngrok / Cloudflare tunnel for mobile access.
- On iOS Safari: Share → **Add to Home Screen**. On Android Chrome: Menu → **Add to Home screen**/**Install app**.

## Benchmarking & Verification
- Run benchmarks: `source venv/bin/activate && PYTHONPATH=. python vaaf/benchmark_runner.py 2>&1 | tee benchmark_results_<tag>.txt`
- Latest structured results live in `benchmark_results.json` and surface via `/api/benchmark/results` for the Insights UI.
- Trigger benchmark + view integrity status directly from **Settings → Audit Trail** (buttons call `/api/benchmark/run` and `/api/verification/verify`).
- Verification receipts are also exposed via `/api/verification/chain`, `/api/verification/receipt/:id`, and `/api/verification/verify` for UI + EigenDA submission.

## Development Notes
- Keep package namespace as `vaaf/` for imports.
- All async pathways (FastAPI, OpenAI) already wired — avoid blocking calls.
- Frontend stays a single-file dark-themed app at `static/index.html` (vanilla JS + CSS only).
- SQLite (`council.db`) stores risk profiles, approvals, actions, and adaptive pre-filter stats.
- Always run `python -c "from server import app; print('All imports OK')"` before committing.
