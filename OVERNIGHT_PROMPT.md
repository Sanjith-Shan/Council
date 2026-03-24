# Council — Overnight Build Instructions

You are working on an open-source project called **Council** (formerly called VAAF). It is an AI agent security framework that intercepts every action an AI agent proposes and evaluates whether the action is beneficial for the user before allowing execution.

## The Codebase

The repo is at: [REPLACE WITH YOUR GITHUB REPO URL]

Clone it if you haven't:
```
git clone [REPO URL] ~/projects/council
```

The project structure:
```
council/
├── server.py               # FastAPI server (port 8001)
├── requirements.txt
├── vaaf/                    # Core modules (keep this directory name for now)
│   ├── models.py            # Pydantic data models
│   ├── council.py           # Review Council (3 parallel classifiers)
│   ├── tier.py              # Tier classifier + pre-filter + command analyzer
│   ├── command_analyzer.py  # Shell command safety classification
│   ├── agent.py             # Standalone agent (used for demo without OpenClaw)
│   ├── risk_profile.py      # Risk profile engine
│   └── audit.py             # Audit logging
├── static/
│   └── index.html           # Web UI (THIS NEEDS MAJOR REDESIGN)
└── integration/             # OpenClaw integration files
    ├── SETUP.md
    ├── patch-openclaw.js
    └── vaaf-plugin/
```

## Your Job

There is a file called TASKS.md in the repo root. It contains a numbered list of tasks. Your job is to complete these tasks one at a time, in order.

**For each task:**

1. Read TASKS.md and find the next uncompleted task (marked with `[ ]`)
2. Complete ALL sub-items in that task
3. Mark it as complete: change `[ ]` to `[x]` in TASKS.md
4. Test your changes to make sure nothing is broken:
   - `cd ~/projects/council && source venv/bin/activate && python -c "from server import app; print('OK')"`
5. Commit and push:
   ```
   cd ~/projects/council
   git add -A
   git commit -m "the commit message specified in the task"
   git push origin main
   ```
6. Stop. The next cron invocation will pick up the next task.

**IMPORTANT RULES:**

- Complete ONE task per invocation. Do not try to do multiple tasks.
- The web UI is a single-file app: everything goes in `static/index.html`. Do not create separate CSS or JS files. Keep it self-contained.
- Do NOT use any external CSS frameworks (no Tailwind CDN, no Bootstrap). Write all CSS from scratch in a `<style>` tag.
- Do NOT use any JavaScript frameworks (no React, no Vue). Use vanilla JS only.
- The UI must work on mobile Safari (iPhone SE viewport: 375px wide). Test your CSS at that width.
- Use only SVG for icons. Do not use emoji as icons in the navigation bar.
- Dark theme: background #0a0a0a, surface #141414, surface2 #1e1e1e, text #e8e8e8, text-muted #888.
- Accent color: #3b82f6 (blue). Success: #22c55e. Warning: #eab308. Danger: #ef4444. Purple: #8b5cf6.
- Font: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif.
- Border radius: 12px for cards, 8px for buttons, 24px for pills.
- All API calls go to the same origin (no hardcoded localhost URLs in the frontend).
- When you change Python code, make sure all imports still work.
- When you rename "VAAF" to "Council", do NOT rename the `vaaf/` Python package directory — just change display text and comments.

**API Endpoints Available:**
```
GET  /api/onboarding          — risk profile questions
POST /api/profile              — update risk profile {answers: {}}
GET  /api/goal                — get current goal
POST /api/goal                — update goal {goal: "..."}
POST /api/chat                — send message {message: "..."}
POST /api/approve             — approve/reject {action_id, approved: bool}
GET  /api/approvals           — pending approvals
GET  /api/activity            — activity feed events
GET  /api/insights            — stats
GET  /api/actions             — all actions (audit trail)
POST /api/evaluate            — external tool evaluation (OpenClaw integration)
GET  /api/evaluate/{id}/status — check approval status
```

**Start now. Read TASKS.md, find the first incomplete task, and complete it.**
