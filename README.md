# Council — AI Agent Security Framework

Council is a dynamic safety layer for AI agents. Instead of static allow/deny lists, Council evaluates every proposed action for policy fit, safety risk, and goal alignment before execution.

## What Council Does

- Intercepts proposed actions before execution
- Fast pre-filter for trivially safe local/read-only actions
- Parallel 3-checker "Council" review (policy, safety, intent)
- Tier-based outcomes: auto-execute, notify, require approval, or block
- First-use escalation for new tools
- SQLite-backed persistence for actions, events, profile, and settings
- Mobile-first PWA dashboard (Chat, Approvals, Activity, Insights, Settings)

## Installation

```bash
git clone https://github.com/Sanjith-Shan/Council.git ~/projects/council
cd ~/projects/council
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set OPENAI_API_KEY in .env
python server.py
```

Open: `http://localhost:8000`

## Architecture (Updated)

```text
User Prompt
  ↓
Primary Agent proposes action
  ↓
Tier Pre-Filter (safe/read-only?)
  ├─ yes → Tier 1 Auto Execute
  └─ no  → Council (3 parallel checkers)
            ├─ Policy checker
            ├─ Safety checker
            └─ Intent checker
                  ↓
              Tier Assignment
              ├─ Tier 2: Execute + notify
              ├─ Tier 3: Queue for user approval
              └─ Tier 4: Block
  ↓
Audit + Activity + Insights persisted in SQLite
```

## How It Works

1. Agent proposes an action (tool + params + reasoning).
2. Pre-filter auto-allows low-risk local/read-only operations.
3. Non-trivial actions go through Council evaluation.
4. Tier classifier decides execution behavior.
5. Result is logged and shown in Activity/Approvals/Insights.

## API Endpoints

- `GET /api/onboarding` — onboarding questions + current profile
- `POST /api/profile` — save risk profile answers
- `POST /api/profile/suggest` — adaptive follow-up profile questions
- `GET /api/goal` — current user goal
- `POST /api/goal` — update user goal
- `GET /api/settings` — retrieve persisted settings
- `POST /api/settings` — update settings
- `POST /api/chat` — send message to agent
- `GET /api/approvals` — list pending approvals
- `POST /api/approve` — approve/reject pending action
- `GET /api/activity` — activity feed events
- `GET /api/insights` — dashboard stats and summary
- `GET /api/actions` — full action audit trail
- `POST /api/evaluate` — OpenClaw/ClawBands interception endpoint
- `GET /api/evaluate/{id}/status` — queued action status lookup

## Mobile App Screenshots (Placeholder)

> Add screenshots here after final UI polish:
>
> - `docs/screenshots/chat.png`
> - `docs/screenshots/approvals.png`
> - `docs/screenshots/activity.png`
> - `docs/screenshots/insights.png`
> - `docs/screenshots/settings.png`

## Connect Council to OpenClaw Gateway

1. Copy env template and set your keys:

```bash
cp .env.example .env
```

2. In `.env`, set:

```env
OPENAI_API_KEY=your-openai-key
OPENCLAW_GATEWAY_TOKEN=your-openclaw-gateway-token
# Optional override (default shown)
OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789
```

3. Start Council and confirm gateway mode:

```bash
source venv/bin/activate
python server.py
# or: ./start.sh
```

4. Verify status:

```bash
curl http://127.0.0.1:8001/api/gateway/status
```

Expected when connected:
- `"connected": true`
- `"mode": "openclaw"`

If token is missing/unreachable, Council automatically falls back to standalone mode.

## Deployment with ngrok (Phone Access)

Use the helper script to run Council on port `8001` and keep logs in your terminal:

```bash
cd ~/projects/council
./start.sh
```

In another terminal, expose it publicly:

```bash
ngrok http 8001
```

Open the HTTPS ngrok URL on your phone, then use browser menu → **Add to Home Screen**.

Tips:
- Keep both the Council terminal and ngrok terminal running.
- If the ngrok URL changes, re-open the new URL from your phone.
- Stop Council with `Ctrl+C` in the `./start.sh` terminal.

## Add to Phone Home Screen

- **iPhone (Safari):** Share → **Add to Home Screen** → Add
- **Android (Chrome):** 3-dot menu → **Add to Home screen** (or **Install app**) → Add

After adding, launch Council from the icon for a standalone PWA-style experience.

## Development Notes

- Keep the Python package directory name as `vaaf/` for import compatibility.
- Frontend remains a single-file app in `static/index.html`.
- Avoid hardcoded localhost API URLs in frontend code.
