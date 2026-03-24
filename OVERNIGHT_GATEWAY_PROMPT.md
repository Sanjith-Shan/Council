# Council — Gateway Integration Build Instructions

You are working on **Council**, an AI agent security framework. The repo is at `~/projects/council`.

## What Council Is

Council is a web app (Python FastAPI backend + vanilla HTML/CSS/JS frontend) that:
1. Evaluates every action an AI agent proposes using a Review Council (3 parallel LLM classifiers)
2. Classifies actions into tiers (auto-execute, notify, approve, block)
3. Shows everything in a mobile-friendly dashboard

## What You're Building Right Now

**You are connecting Council's chat interface to the OpenClaw gateway** so that users can talk to their OpenClaw agent directly through Council's web UI instead of Discord.

OpenClaw exposes an OpenAI-compatible API at `http://127.0.0.1:18789/v1/chat/completions`. You send messages there with `model: "openclaw:main"` and a Bearer token for auth. That's all the integration needs.

## The Task File

Read `~/projects/council/TASKS_GATEWAY.md`. It has 10 numbered tasks. Find the next one that's not marked `[x]` and complete it.

## Rules

1. **ONE task per invocation.** Complete it fully, test, commit, push, stop.

2. **Test before committing:**
   ```bash
   cd ~/projects/council
   source venv/bin/activate
   python -c "from server import app; print('Server imports OK')"
   ```

3. **Commit and push after each task:**
   ```bash
   cd ~/projects/council
   git add -A
   git commit -m "the commit message from the task"
   git push origin main
   ```

4. **Mark the task complete** in TASKS_GATEWAY.md: change `[ ]` to `[x]`

5. **The frontend is a single file:** `static/index.html`. All CSS in `<style>`, all JS in `<script>`. No external frameworks.

6. **Design rules for the UI:**
   - Dark theme: bg #0a0a0a, surface #141414, surface2 #1e1e1e
   - Text: #e8e8e8 primary, #888 muted
   - Accent: #3b82f6 blue, #22c55e green, #eab308 yellow, #ef4444 red
   - Font: -apple-system, BlinkMacSystemFont, system-ui, sans-serif
   - Border-radius: 12px cards, 8px buttons
   - Mobile-first: must work at 375px width
   - No emoji as icons — use SVG

7. **Python code rules:**
   - Keep vaaf/ as the package directory name
   - All new modules go in vaaf/
   - Use async/await for all I/O
   - Error handling: never let the server crash — catch and return error responses

8. **The gateway token** can be found by running: `openclaw config get gateway.auth.token`

9. **Do NOT modify OpenClaw's files.** Only modify files in ~/projects/council/

## Project Structure
```
council/
├── server.py               # FastAPI server
├── requirements.txt
├── .env                     # API keys (OPENAI_API_KEY, OPENCLAW_GATEWAY_TOKEN)
├── .env.example
├── start.sh                 # Startup script (create in Task 9)
├── TASKS_GATEWAY.md         # Task list — mark tasks [x] as you complete them
├── vaaf/
│   ├── __init__.py
│   ├── models.py
│   ├── council.py           # Review Council
│   ├── tier.py              # Tier classifier
│   ├── command_analyzer.py  # Shell command safety classification
│   ├── agent.py             # Standalone agent (fallback)
│   ├── risk_profile.py
│   ├── audit.py
│   ├── database.py          # SQLite storage (may exist from prior tasks)
│   └── openclaw_client.py   # CREATE THIS — OpenClaw gateway client
├── static/
│   └── index.html           # Web UI
└── integration/
    ├── SETUP.md
    ├── patch-openclaw.js
    └── vaaf-plugin/
```

## Start now. Read TASKS_GATEWAY.md and complete the next incomplete task.
