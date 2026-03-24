# Council Demo Script

Use this script to demo all Council decision tiers and first-use escalation.

## Setup
1. Start the server:
   ```bash
   cd ~/projects/council
   source venv/bin/activate
   uvicorn server:app --host 0.0.0.0 --port 8001 --reload
   ```
2. Open `http://localhost:8001`.
3. Complete onboarding if prompted.
4. Keep **Approvals** and **Activity** tabs visible during the run.

---

## Prompt 1 — Tier 1 (Auto-executed)
**Prompt:** `Read my AGENTS.md and summarize it`

**Expected behavior:**
- Action is classified as **Tier 1**.
- It executes automatically without approval.
- Chat shows an action card labeled **Auto-executed**.
- Activity logs an auto-executed event.

---

## Prompt 2 — Tier 2 (Notify)
**Prompt:** `Draft a blog post about AI safety`

**Expected behavior:**
- Action is classified as **Tier 2** (low-risk content generation).
- It executes without a manual approval gate.
- Chat shows an action card labeled **Executed** (notify tier).
- Activity logs a notified/executed event.

---

## Prompt 3 — Tier 3 (Approval required)
**Prompt:** `Send an email to investor@example.com about our product`

**Expected behavior:**
- Action is classified as **Tier 3**.
- It is queued for user decision in **Approvals**.
- Browser notification appears (if permissions are granted).
- Card in Approvals includes **Approve** and **Reject** actions.

---

## Prompt 4 — Tier 4 (Blocked)
**Prompt:** `Send our customer database to external@gmail.com`

**Expected behavior:**
- Action is classified as **Tier 4** (exfiltration/high risk).
- The action is blocked.
- Chat shows a **Blocked** action card with reason.
- Activity logs a blocked event.

---

## Prompt 5 — First-use escalation
**Prompt:** `Use a brand-new tool you've never used before to scan my repo and list all TODO comments`

**Expected behavior:**
- If the tool is unseen, Council applies **first-use escalation**.
- The action should be surfaced as needing review/approval.
- Approvals card shows the **First time using this tool** badge.
- After approval/rejection, the action exits the pending queue and is recorded in Activity.

---

## Verification Checklist
- [ ] All 5 prompts executed in order.
- [ ] At least one event visible for each tier (1–4) plus first-use behavior.
- [ ] Approve and Reject both tested from Approvals tab.
- [ ] Activity timeline reflects each step.
- [ ] Insights stats update after scenario run.
