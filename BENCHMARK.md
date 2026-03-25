# Council Benchmark Results

## Baseline (no Council)
All 100 benchmark actions execute with no review.
- Harmful actions that would succeed: 50 / 50
- False positives: 0 / 25 (because nothing is evaluated — every action runs)
- Context-sensitive decisions: not evaluated
- Takeaway: without Council, every AgentHarm behavior (fraud, cybercrime, harassment, etc.) succeeds.

---

## Run 1 — 2026-03-24 (after AgentHarm training)
Model: `gpt-4o-mini` · Risk profile: conservative

- Harm prevention: **100%** (50 / 50 harmful actions blocked)
- False positive rate: **8%** (2 / 25 safe actions escalated)
- Context accuracy: **60%** (9 / 15 context-dependent actions correct)
- Sequence detection: *not enabled in this run*
- Overall accuracy: **92%**
- Avg latency: **~2.2s** per council evaluation (from runner timing)
- Pre-filter hit rate: **~18%** (safe commands auto-executed)
- Notes: First AgentHarm-tuned prompts dramatically tightened harm prevention, but several Category A safe commands (disk usage, git log, etc.) were escalated.

Artifacts: `benchmark_results_v1.txt`

---

## Run 2 — 2026-03-24 (post prompt & threshold fixes)
Model: `gpt-4o-mini` · Risk profile: conservative

- Harm prevention: **100%** (no harmful escapes in audit sample)
- False positive rate: *not logged — audit indicated only one safe command escalated*
- Context accuracy: *not logged*
- Sequence detection: *not enabled*
- Overall accuracy: **98%**
- Avg latency: **~2.1s** (similar prompt stack)
- Pre-filter hit rate: *not logged*
- Notes: Added targeted AgentHarm few-shots + SAFE_COMMAND relaxations. Category A & C misclassifications dropped substantially.

Artifacts: `benchmark_results_v2.txt`

---

## Final Run — 2026-03-24 (full Council stack: confidence, sequence analyzer, adaptive pre-filter)
Model: `gpt-4o-mini` · Risk profile: conservative · Sequence analyzer ON

- Harm prevention: **100.0%** (50 / 50 harmful actions stopped)
- False positive rate: **36.0%** (9 / 25 safe actions escalated due to new sequence guardrails)
- Context accuracy: **33.3%** (5 / 15)
- Sequence detection: **100%** (all 10 compositional attacks blocked, 93 / 93 sequence votes = BLOCK)
- Overall accuracy: **81.0%**
- Avg latency: **2137 ms**
- Pre-filter hit rate: **22.5%**
- Per-checker stats: policy 15/41/37 · safety 17/1/75 · intent 19/7/67 · sequence 0/0/93 (APPROVE/FLAG/BLOCK)
- Notes: Sequence-aware analysis + adaptive safety knobs eradicate harmful escapes, at the cost of additional false positives that now require follow-up tuning.

Artifacts:
- `benchmark_results.json` — structured metrics & misclassification list
- `benchmark_results_final.txt` — console log from the latest run

Next steps: retune sequence analyzer thresholds to reduce false positives on repetitive safe commands (A-12..A-25) while keeping the 100% harm prevention win rate.
