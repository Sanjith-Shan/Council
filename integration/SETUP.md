# Council + OpenClaw Integration Setup

This guide connects OpenClaw action execution to Council review.

## Prerequisites

- OpenClaw installed (`openclaw --version`)
- Python 3.10+
- Node.js 18+
- `OPENAI_API_KEY` configured in Council `.env`

## 1) Start Council

```bash
cd ~/projects/council
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # first time only
python server.py
```

Expected server URL: `http://localhost:8000`

## 2) Patch OpenClaw (recommended demo path)

```bash
cd ~/projects/council/integration
node patch-openclaw.js
```

You should see logs prefixed with `[Council]` and a success message.

To revert:

```bash
node patch-openclaw.js --revert
```

## 3) Restart OpenClaw Gateway

```bash
openclaw gateway restart
```

## 4) Validate End-to-End

1. Open `http://localhost:8000`
2. Trigger an agent action from OpenClaw
3. Confirm events appear in **Activity**
4. Confirm approval-required actions appear in **Approvals**
5. Approve/reject and confirm status updates

## API Contract for Integrations

Council expects:

`POST /api/evaluate`

```json
{
  "tool_name": "exec",
  "arguments": {"command": "ls -la"},
  "description": "List workspace files",
  "context": "optional agent context"
}
```

And returns tier/status information with optional approval queueing.

For queued actions:

- `GET /api/evaluate/{id}/status`

## Troubleshooting

- If no actions appear in Council, re-run patch and restart gateway.
- If Council returns errors, verify `OPENAI_API_KEY` and Python deps.
- If frontend cannot load data, confirm same-origin access at `http://localhost:8000`.
