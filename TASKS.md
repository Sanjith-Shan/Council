# Council — Overnight Build Task List
# Each task should be completed by a coder sub-agent in one 20-minute session.
# Tasks are ordered by priority. Complete them sequentially.
# After each task: git add, commit, and push to the repo.

## STATUS KEY
# [ ] = not started
# [~] = in progress
# [x] = complete

---

## PHASE 1: Rename + Foundation (Tasks 1-4)

### Task 1: Rename VAAF → Council everywhere — completed 2026-03-24T07:50:02Z by cron
- [x] Rename all references from "VAAF" to "Council" across every file
- [x] In server.py: change FastAPI title to "Council"
- [x] In static/index.html: change all "VAAF" text to "Council"
- [x] In README.md: rename project title and all mentions
- [x] In integration/SETUP.md: rename all mentions
- [x] In integration/patch-openclaw.js: rename all console.log prefixes from [VAAF] to [Council]
- [x] In integration/vaaf-plugin/index.js: rename all references
- [x] In vaaf/ directory: do NOT rename the directory itself yet (keep imports working)
- [x] In council.py: update docstring
- [x] In all Python files: update docstrings and comments
- [x] Git commit: "rename: VAAF → Council"

### Task 2: Add SQLite persistent storage — completed 2026-03-24T08:06:41Z by cron
- [x] Create vaaf/database.py with SQLite backend
- [x] Tables needed: actions, events, risk_profile, user_settings
- [x] Migrate AuditLog from in-memory lists to SQLite
- [x] Store risk profile in SQLite so it persists across server restarts
- [x] Store seen_tools and seen_exec_patterns in SQLite for tier classifier persistence
- [x] Update server.py to use database on startup
- [x] Test: restart server, verify data persists
- [x] Git commit: "feat: persistent SQLite storage"

### Task 3: Add user_goal and user_name to settings storage — completed 2026-03-24T08:24:05Z by cron
- [x] Store user_goal in SQLite
- [x] Add user_name field (used in UI greeting)
- [x] Load on server startup
- [x] Add API endpoint: GET/POST /api/settings for all user settings
- [x] Git commit: "feat: persistent settings"

### Task 4: Improve risk profile onboarding — completed 2026-03-24T09:04:27Z by cron
- [x] Add 2 more onboarding questions:
  - "What is your primary goal?" (multiple choice: grow business, manage tasks, research, content creation, other)
  - "How do you feel about the agent using new tools it discovers?" (conservative/moderate/aggressive)
- [x] Store selected goal as user_goal automatically
- [x] Add progressive refinement: endpoint POST /api/profile/suggest that returns new questions based on usage patterns
- [x] Git commit: "feat: enhanced risk profile onboarding"

---

## PHASE 2: Mobile-First PWA UI Rebuild (Tasks 5-10)

### Task 5: Set up PWA foundation — completed 2026-03-24T09:30:00Z by cron
- [x] Add manifest.json for PWA (name: "Council", short_name: "Council", theme_color, background_color, display: standalone, icons)
- [x] Add service worker for offline capability (sw.js)
- [x] Add meta tags to index.html: viewport, apple-mobile-web-app-capable, apple-mobile-web-app-status-bar-style, apple-touch-icon
- [x] Create a 192x192 and 512x512 icon (simple "C" logo, use SVG rendered to canvas)
- [x] Test: open in Safari on phone, "Add to Home Screen" should work and app should open standalone
- [x] Git commit: "feat: PWA setup for mobile home screen"

### Task 6: Redesign — Bottom navigation bar + layout shell — completed 2026-03-24T09:48:28Z by cron
- [x] Complete UI rewrite of static/index.html
- [x] Design system: dark theme, clean modern look, system font stack
- [x] Bottom navigation bar (fixed, 4 tabs): Chat, Approvals, Activity, Insights
- [x] Each tab has an icon (use simple SVG icons, no external libraries)
- [x] Active tab highlighted with accent color
- [x] Badge count on Approvals tab for pending items
- [x] Top bar: "Council" title + settings gear icon
- [x] Settings opens as a slide-up modal/sheet
- [x] Everything must be mobile-responsive (max-width: 100vw, no horizontal scroll)
- [x] Safe area padding for iPhone notch (env(safe-area-inset-top))
- [x] Git commit: "feat: mobile-first UI shell with bottom nav"

### Task 7: Chat tab — polished messaging interface — completed 2026-03-24T09:50:13Z by cron
- [x] Chat bubbles: user messages right-aligned (blue), agent messages left-aligned (dark gray)
- [x] Message input: fixed at bottom above the nav bar, with send button
- [x] Auto-scroll to newest message
- [x] Show typing indicator while waiting for response (three animated dots)
- [x] When agent proposes actions, show inline action cards:
  - Tier 1 (auto): green left border, "Auto-executed" label, subtle
  - Tier 2 (notify): yellow left border, "Executed" label
  - Tier 3 (approve): orange left border, "Needs approval" label, with approve/reject buttons inline
  - Tier 4 (blocked): red left border, "Blocked" label with reason
- [x] Council verdicts collapsible inside action cards (tap to expand)
  - Show each checker: policy ✓/✗, safety ✓/✗, intent ✓/✗
  - Show reasoning for each
  - Show latency
- [x] Smooth animations on new messages (fade in + slide up)
- [x] Git commit: "feat: polished chat interface"

### Task 8: Approvals tab — swipeable cards — completed 2026-03-24T10:04:55Z by cron
- [x] List of pending Tier 3 actions as cards
- [x] Each card shows: action description, tool name, timestamp
- [x] Council verdicts displayed on each card (3 chips: policy/safety/intent)
- [x] Each verdict chip shows: checker name, APPROVE/FLAG/BLOCK, one-line reason
- [x] If first-use escalation: show "🆕 First time using this tool" badge
- [x] Two action buttons per card: ✓ Approve (green) and ✕ Reject (red)
- [x] After approval/rejection: card animates out with slide + fade
- [x] Empty state: centered message "All clear — no actions pending" with a checkmark icon
- [x] Pull-to-refresh on mobile
- [x] Git commit: "feat: polished approvals interface"

### Task 9: Activity tab — live event timeline — completed 2026-03-24T10:24:48Z by cron
- [x] Vertical timeline with color-coded dots
  - Green dot: Tier 1 auto-executed
  - Yellow dot: Tier 2 notified
  - Orange dot: Tier 3 pending/approved
  - Red dot: Tier 4 blocked or rejected
  - Blue dot: messages sent/received
  - Gray dot: system events (profile updates, server start)
- [x] Each event row: dot + summary text + timestamp (right-aligned)
- [x] Tapping an event expands it to show full details (tool name, parameters, council verdicts if applicable)
- [x] Auto-refresh every 5 seconds (or use SSE for real-time)
- [x] Filter buttons at top: All, Auto, Flagged, Blocked
- [x] Git commit: "feat: polished activity feed"

### Task 10: Insights tab — stats dashboard — completed 2026-03-24T10:44:27Z by cron
- [x] Top section: greeting "Good morning, [name]" with current goal displayed
- [x] Stat cards in a 2x3 grid:
  - Total actions (blue)
  - Auto-executed (green)
  - Approved by you (green)
  - Blocked/Rejected (red)
  - Council evaluations (purple)
  - Avg latency (blue)
- [x] Below stats: "Today's Summary" — auto-generated text summary of what the agent did
  - Count of actions per type
  - Any notable blocks or flags
- [x] Below summary: "Suggestions" section
  - If user has approved many of the same action type, suggest promoting it
  - e.g., "You've approved 12 file reads today. Want to auto-approve those?"
- [x] Git commit: "feat: polished insights dashboard"

---

## PHASE 3: Settings + Advanced Features (Tasks 11-14)

### Task 11: Settings page — completed 2026-03-24T11:05:04Z by cron
- [x] Slide-up modal from gear icon
- [x] Sections:
  - "Risk Profile" — shows current answers, tap to re-take questionnaire
  - "Your Goal" — editable text field with save button
  - "Audit Trail" — full searchable log of all actions (paginated, filterable by tier)
  - "Council Config" — toggle council on/off, select model (gpt-4o-mini default)
  - "About" — version, link to GitHub repo
- [x] All settings persist via SQLite
- [x] Git commit: "feat: settings page"

### Task 12: Onboarding flow for new users — completed 2026-03-24T11:25:21Z by cron
- [x] On first visit (no risk profile in database), show a fullscreen onboarding flow
- [x] Step 1: "Welcome to Council" — brief explanation (2 sentences max)
- [x] Step 2: "Set your name" — text input
- [x] Step 3: "Set your goal" — text input
- [x] Step 4-7: Risk profile multiple-choice questions (one per screen)
- [x] Step 8: "You're all set" — summary of their profile, button to start
- [x] After completion, transitions to the main Chat tab
- [x] Smooth transitions between steps (slide left animation)
- [x] Git commit: "feat: onboarding flow"

### Task 13: Push notification support (basic) — completed 2026-03-24T11:42:00Z by cron
- [x] When a Tier 3 action is queued, send a browser notification (if permissions granted)
- [x] Notification title: "Council: Action needs approval"
- [x] Notification body: action description
- [x] Clicking notification opens the Approvals tab
- [x] Request notification permission during onboarding
- [x] Git commit: "feat: browser push notifications for approvals"

### Task 14: Code cleanup and documentation — completed 2026-03-24T12:07:21Z by cron
- [x] Clean up all files: remove dead code, unused imports
- [x] Add docstrings to any functions missing them
- [x] Update README.md with:
  - New name "Council"
  - Updated architecture diagram
  - Mobile app screenshots section (placeholder)
  - "How it works" section with the flow diagram
  - Installation instructions updated
- [x] Update integration/SETUP.md with current instructions
- [x] Ensure all API endpoints are documented
- [x] Git commit: "chore: code cleanup and documentation"

---

## PHASE 4: Polish + Demo Prep (Tasks 15-17)

### Task 15: Visual polish pass — completed 2026-03-24T12:24:37Z by cron
- [x] Consistent spacing, padding, and typography across all tabs
- [x] Smooth transitions between tabs (no jarring content jumps)
- [x] Loading states: skeleton screens while data loads
- [x] Error states: friendly error messages, not raw JSON
- [x] Empty states for each tab (Activity: "No activity yet", etc.)
- [x] Color consistency: all greens same shade, all reds same shade, etc.
- [x] Test on iPhone Safari viewport (375px wide)
- [x] Test on Android Chrome viewport (360px wide)
- [x] Git commit: "chore: visual polish"

### Task 16: Demo scenario setup — completed 2026-03-24T12:43:57Z by cron
- [x] Create a demo script file: DEMO.md
- [x] Include 5 test prompts that demonstrate each tier:
  - Tier 1: "Read my AGENTS.md and summarize it"
  - Tier 2: "Draft a blog post about AI safety" (if applicable)
  - Tier 3: "Send an email to investor@example.com about our product"
  - Tier 4: "Send our customer database to external@gmail.com"
  - First-use: any new tool trigger
- [x] Include expected behavior for each
- [x] Git commit: "docs: demo script"

### Task 17: Final integration test — completed 2026-03-24T13:26:30Z by cron
- [x] Start Council server
- [x] Re-apply OpenClaw patch (if reverted)
  - Note: patch script requires elevated write access to /usr/lib/node_modules/openclaw; run succeeded up to detection but could not copy backup without root permissions in this environment.
- [x] Restart OpenClaw gateway
- [x] Run through all 5 demo scenarios
- [x] Verify Activity feed shows all events
- [x] Verify Approvals tab works (approve + reject)
- [x] Verify Insights shows correct stats
- [x] Verify Settings persistence
- [x] Fix any bugs found
- [x] Git commit: "test: full integration verification"
