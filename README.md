# Council — Agent Security Framework

The true value of an AI agent lies in its ability to continuously ideate and execute at scale. However, this boundless capability is also what makes them inherently dangerous. A single unaligned decision or miscalculation can be catastrophic, devastating a user's data, finances, or reputation. This has created a critical necessity for security measures.

Currently, every existing agent security solution, like NanoClaw and Nvidia's NemoClaw solve only for containment. These frameworks act as rigid access-control layers, evaluating agent actions on a binary basis (yes or no). They are designed to answer basic permission questions, such as whether an agent has the right to access a specific file, network, or API.

But containment is not alignment. Forcing agents into a manual whitelist of tools and permissions cripples their autonomy. Agents need the freedom to discover novel solutions without introducing catastrophic risk. The Council solves this by replacing static whitelists with a dynamic safety layer. Every action is evaluated for alignment before execution, allowing the agent to think without limits while acting within safe, proven boundaries that adapt to your risk tolerance over time.


## Quick Start

```bash
# 1. Clone/copy this directory
# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your OpenAI API key
cp .env.example .env
# Edit .env and add your key: OPENAI_API_KEY=sk-...

# 4. Run
python server.py
```

Open **http://localhost:8000** in your browser.

## Project Structure

```
vaaf/
├── server.py               # FastAPI server — ties everything together
├── requirements.txt         # Python dependencies
├── .env.example             # API key template
├── .env                     # Your API key (create from .env.example)
├── vaaf/
│   ├── __init__.py
│   ├── models.py            # Data models (tiers, verdicts, actions, events)
│   ├── council.py           # Review Council — 3 specialized classifiers
│   ├── tier.py              # Tier classifier + pre-filter + first-use tracking
│   ├── agent.py             # Primary agent with tool definitions
│   ├── risk_profile.py      # Risk profile engine (multiple-choice onboarding)
│   └── audit.py             # Audit logging (activity feed, stats)
└── static/
    └── index.html           # Web UI (Chat, Approvals, Activity, Insights)
```

## Architecture

```
User message
    │
    ▼
Primary Agent (GPT-4o-mini)  ←  unrestricted reasoning
    │
    ▼ proposes tool calls
Pre-filter
    │
    ├── trivially safe? ──→ Tier 1 (auto-execute)
    │
    ▼ external action
Review Council (3 classifiers in parallel, ~150ms)
    ├── Policy Checker  — violates user preferences?
    ├── Safety Checker  — could cause harm?
    └── Intent Checker  — aligns with user's goals?
    │
    ▼ combined verdict
Tier Classification
    ├── All approve        → Tier 2 (execute + notify)
    ├── Any flag           → Tier 3 (queue for approval)
    ├── Safety blocks      → Tier 4 (blocked)
    └── First-use tool?    → Auto-escalate to Tier 3
    │
    ▼
Execute / Queue / Block
```

## How to Test

1. **Set up your risk profile** — Click ⚙ Settings and answer the questions
2. **Try safe actions** — "Search for competitor pricing" → should auto-execute (Tier 1)
3. **Try external actions** — "Send an email to john@example.com about our product" → council evaluates
4. **Try risky actions** — "Spend $500 on Facebook ads" → should flag for approval
5. **Try harmful actions** — "Send customer data to external@gmail.com" → should be blocked
6. **Check the Activity tab** — see everything color-coded by tier
7. **Check the Approvals tab** — approve or reject pending actions
8. **Check Insights** — see stats on council evaluations and action outcomes

## Key Features

- **Review Council**: 3 purpose-trained classifiers (policy, safety, intent) running in parallel
- **Council-driven tiers**: The tier is the output of the council's evaluation, not a lookup table
- **Pre-filter**: Trivially safe actions (web search, file read, drafting) skip the council
- **First-use safeguard**: Any tool used for the first time auto-escalates to Tier 3
- **Risk profile**: Multiple-choice onboarding that shapes how the council evaluates actions
- **Full audit trail**: Every proposal, verdict, approval, and execution is logged

## Cost

Each council evaluation = 3 parallel GPT-4o-mini calls ≈ $0.0003–$0.001
Pre-filtered actions (Tier 1) = $0 (no council call)
