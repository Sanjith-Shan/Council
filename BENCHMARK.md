# Council Benchmark Results

## Baseline (no Council)
All 100 actions execute unchecked. 0% harm prevention.

## With Council — gpt-5.4-nano
- **Harm prevention: 100%** (50/50 harmful actions caught)
- **False positive rate: 36%** (9/25 safe actions over-flagged)
- **Context accuracy: 6.7%**
- **Sequence detection: 100%** (10/10 sequences caught)
- **Overall accuracy: 77%**
- **Avg latency: 835ms** per evaluation
- **Pre-filter hit rate: 22.5%** (skipped council for trivially safe actions)

## Analysis
The system errs heavily on the side of caution — zero harmful actions slip through, but safe actions are sometimes flagged unnecessarily. The fine-tuned gpt-4.1-nano classifier (currently training) is expected to reduce the false positive rate while maintaining harm prevention.

## Methodology
- 100 test scenarios: 50 AgentHarm harmful + 25 safe + 15 context + 10 sequences
- AgentHarm benchmark (ICLR 2025) — MIT license for safety research
- Test scenarios do NOT overlap with classifier training data
