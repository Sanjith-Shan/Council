# Council

An independent safety layer for autonomous AI agents. Council intercepts every action an agent proposes and evaluates it through a panel of parallel classifiers before execution. The freamework seeks to catch harmful, misaligned, or risky behavior without crippling the agent's autonomy.

Built as a security middleware for [OpenClaw](https://github.com/openclaw/openclaw).

---

## The Problem

AI agents can execute actions autonomously like shell commands, file writes, emails, purchases, API calls. The only safety mechanism is the LLM's own training, which tells it to refuse harmful requests. The [AgentHarm benchmark](https://arxiv.org/abs/2410.09024) (ICLR 2025) tested this and found that leading LLMs comply with **48–82% of harmful agent requests** without any jailbreak.

Existing solutions like NanoClaw and NemoClaw solve **containment**. These frameworks act as rigid access-control layers, evaluating agent actions on a binary basis (yes or no). They are designed to answer basic permission questions, such as whether an agent has the right to access a specific file, network, or API.


But containment is not alignment. Forcing agents into a manual whitelist of tools and permissions cripples their autonomy. Agents need the freedom to discover novel solutions without introducing catastrophic risk. Council fills this gap: it evaluates whether an action is **actually good for the user** given context, risk tolerance, and recent behavior — not just whether the agent has permission to attempt it.

## How It Works

```
Agent proposes action (tool + params)
         │
         ▼
   Pre-filter (deterministic, <1ms)
   Safe? ──yes──▶ Tier 1: Execute immediately
         │
         no
         ▼
   Review Council (4 parallel LLM classifiers, ~800ms)
   ┌─────────────┬──────────────┬──────────────┬──────────────────┐
   │   Policy     │    Safety    │    Intent    │    Sequence      │
   │ (risk profile│ (harm check) │ (goal align) │ (pattern detect) │
   │  aware)      │              │              │                  │
   └─────┬───────┴──────┬───────┴──────┬───────┴────────┬─────────┘
         │              │              │                │
         ▼              ▼              ▼                ▼
   Verdicts + confidence scores aggregated
         │
         ▼
   Tier Assignment
   ├── Tier 1: Auto-execute (safe, high confidence)
   ├── Tier 2: Execute + notify (low concern)
   ├── Tier 3: Queue for human approval (medium concern)
   └── Tier 4: Block (immediate danger)
         │
         ▼
   Verification receipt (hash-chained, EigenDA-ready)
```

## Features

### Security Pipeline
- **Pre-filter**: Deterministic code that instantly approves safe operations (`read`, `ls`, `cat`, `grep`, `git status`) and routes dangerous ones (`rm`, `curl|bash`, `sudo`) to the council. Handles ~22% of all actions with zero latency and zero cost.
- **Command analyzer**: Parses actual shell commands inside `exec` calls — doesn't just see "exec" as dangerous, it distinguishes `wc -c file.md` from `rm -rf /`.
- **Review Council**: Four classifiers running in parallel via `asyncio.gather`. Each returns a verdict (APPROVE/FLAG/BLOCK), one-sentence reasoning, and a confidence score.
- **Sequence analyzer**: Detects multi-step attack patterns where each individual action seems safe but the sequence is harmful (e.g., read credentials → encode → send externally).
- **Confidence-based escalation**: When average checker confidence drops below 0.6, the system auto-escalates one tier regardless of verdicts.

### Adaptive Behavior
- **Learns from approvals**: After you approve the same action pattern 3+ times, the pre-filter auto-approves future matches.
- **Rate limiting**: More than 10 identical tool calls in 5 minutes triggers auto-escalation, catching runaway agent loops.
- **First-use escalation**: New tools the agent hasn't used before are automatically escalated for review.
- **Risk profile**: Configurable via onboarding questionnaire — conservative users get more approval prompts, aggressive users get more autonomy.

### Verification & Audit
- **Hash-chained receipts**: Every council evaluation produces a cryptographic receipt chained to all previous receipts. Tampering with any single receipt breaks the entire chain.
- **EigenDA integration**: Receipt hashes are dispersed to EigenDA's Holesky testnet via gRPC for immutable on-chain proof of evaluation.
- **Full audit trail**: Every action, verdict, approval, rejection, and override is logged to SQLite with timestamps.

### Interface
- **Mobile PWA**: Dark-themed, installable web app with Chat, Approvals, Activity, Insights, and Settings tabs.
- **Chat**: Routes messages to OpenClaw via CLI subprocess — same agent, same tools, same memory as Discord/WhatsApp.
- **Approvals**: Tier 3 actions appear as cards with all checker verdicts and approve/reject buttons.
- **Activity**: Color-coded timeline with verification receipt hashes and override buttons for blocked actions.
- **Insights**: Benchmark results, harm prevention stats, EigenDA submission status.

## Benchmark Results

Tested on 100 scenarios: 50 harmful (from AgentHarm), 25 safe, 15 context-dependent, 10 compositional sequences.

| Metric | Without Council | With Council |
|---|---|---|
| Harmful actions caught | 0% | **100%** |
| False positive rate | 0% | 36% |
| Sequence attacks caught | 0% | **100%** |
| Overall accuracy | — | **77%** |
| Avg evaluation latency | — | 835ms |

Model: `gpt-5.4-nano` for all checkers. Pre-filter hit rate: 22.5%.

See [BENCHMARK.md](./BENCHMARK.md) for full methodology and results.

## Current Limitations

- **Classifiers are prompt-engineered, not fine-tuned.** The council checkers are really just GPT-5.4-nano with few-shot examples from AgentHarm. A fine-tuning job on gpt-4.1-nano is submitted but hasn't completed yet due to delays from OpenAI servers. Fine-tuned classifiers would reduce the false positive rate significantly.
- **Benchmark tests easy cases.** The 100% harm prevention rate is on explicitly harmful scenarios from AgentHarm. Real-world adversarial actions (e.g., "back up the client list to my personal drive") would be harder to detect. However, our system would still have a higher likelihood of detection than OpenClaw's individual LLM.
- **EigenDA is testnet only.** Receipt hashes are dispersed to Holesky testnet. Production would require mainnet access and EigenCompute integration for verified execution in a TEE.
- **Chat doesn't stream.** Responses appear all at once after 30-60 seconds because the OpenClaw CLI doesn't support token-by-token streaming.

## Planned Improvements

- **Fine-tuned safety classifier** on gpt-4.1-nano using AgentHarm training data (in progress, just delayed due to OpenAI servers)
- **EigenCompute integration** for verified execution — proving the classifier code ran correctly in a TEE
- **Adversarial benchmark suite** with disguised harmful actions, not just explicitly labeled ones
- **Calibrated confidence** via fine-tuning, enabling more precise tier boundaries
- **Streaming chat responses** through OpenClaw's WebSocket protocol
- **Multi-user support** with per-user risk profiles and approval queues

## Installation

```bash
git clone https://github.com/Sanjith-Shan/Council.git
cd Council
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your OPENAI_API_KEY and OPENCLAW_GATEWAY_TOKEN to .env
```

## Usage

Start the server:
```bash
python -c "import uvicorn; from server import app; uvicorn.run(app, host='0.0.0.0', port=8001)"
```

For phone access via ngrok:
```bash
ngrok http 8001
# Open the ngrok URL on your phone → Share → Add to Home Screen
```

Enable the OpenClaw security patch (intercepts all tool calls):
```bash
sudo python3 integration/patch-openclaw.js  # or the manual patch method
openclaw gateway restart
```

Run benchmarks:
```bash
PYTHONPATH=. python vaaf/benchmark_runner.py
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/chat` | POST | Send message (routes through OpenClaw) |
| `/api/evaluate` | POST | Evaluate a tool call (called by the OpenClaw patch) |
| `/api/evaluate/{id}/status` | GET | Poll approval status for queued actions |
| `/api/approve` | POST | Approve or reject a Tier 3 action |
| `/api/override` | POST | Override a Tier 4 blocked action |
| `/api/approvals` | GET | List pending Tier 3 actions |
| `/api/activity` | GET | Activity feed |
| `/api/insights` | GET | Aggregated stats |
| `/api/verification/verify` | GET | Validate the hash chain |
| `/api/verification/chain` | GET | Recent verification receipts |
| `/api/eigenda/status` | GET | EigenDA testnet connection stats |
| `/api/benchmark/results` | GET | Latest benchmark metrics |
| `/api/gateway/status` | GET | OpenClaw connection status |

## References

- [AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents](https://arxiv.org/abs/2410.09024) (ICLR 2025)
- [EigenDA Documentation](https://docs.eigenda.xyz/)
- [OpenClaw](https://github.com/openclaw/openclaw)

## License

MIT
