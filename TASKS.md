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
- [ ] Git commit: "feat: persistent settings"

### Task 4: Improve risk profile onboarding
- [ ] Add 2 more onboarding questions:
  - "What is your primary goal?" (multiple choice: grow business, manage tasks, research, content creation, other)
  - "How do you feel about the agent using new tools it discovers?" (conservative/moderate/aggressive)
- [ ] Store selected goal as user_goal automatically
- [ ] Add progressive refinement: endpoint POST /api/profile/suggest that returns new questions based on usage patterns
- [ ] Git commit: "feat: enhanced risk profile onboarding"

---

## PHASE 2: Mobile-First PWA UI Rebuild (Tasks 5-10)

### Task 5: Set up PWA foundation
- [ ] Add manifest.json for PWA (name: "Council", short_name: "Council", theme_color, background_color, display: standalone, icons)
- [ ] Add service worker for offline capability (sw.js)
- [ ] Add meta tags to index.html: viewport, apple-mobile-web-app-capable, apple-mobile-web-app-status-bar-style, apple-touch-icon
- [ ] Create a 192x192 and 512x512 icon (simple "C" logo, use SVG rendered to canvas)
- [ ] Test: open in Safari on phone, "Add to Home Screen" should work and app should open standalone
- [ ] Git commit: "feat: PWA setup for mobile home screen"

### Task 6: Redesign — Bottom navigation bar + layout shell
- [ ] Complete UI rewrite of static/index.html
- [ ] Design system: dark theme, clean modern look, system font stack
- [ ] Bottom navigation bar (fixed, 4 tabs): Chat, Approvals, Activity, Insights
- [ ] Each tab has an icon (use simple SVG icons, no external libraries)
- [ ] Active tab highlighted with accent color
- [ ] Badge count on Approvals tab for pending items
- [ ] Top bar: "Council" title + settings gear icon
- [ ] Settings opens as a slide-up modal/sheet
- [ ] Everything must be mobile-responsive (max-width: 100vw, no horizontal scroll)
- [ ] Safe area padding for iPhone notch (env(safe-area-inset-top))
- [ ] Git commit: "feat: mobile-first UI shell with bottom nav"

### Task 7: Chat tab — polished messaging interface
- [ ] Chat bubbles: user messages right-aligned (blue), agent messages left-aligned (dark gray)
- [ ] Message input: fixed at bottom above the nav bar, with send button
- [ ] Auto-scroll to newest message
- [ ] Show typing indicator while waiting for response (three animated dots)
- [ ] When agent proposes actions, show inline action cards:
  - Tier 1 (auto): green left border, "Auto-executed" label, subtle
  - Tier 2 (notify): yellow left border, "Executed" label
  - Tier 3 (approve): orange left border, "Needs approval" label, with approve/reject buttons inline
  - Tier 4 (blocked): red left border, "Blocked" label with reason
- [ ] Council verdicts collapsible inside action cards (tap to expand)
  - Show each checker: policy ✓/✗, safety ✓/✗, intent ✓/✗
  - Show reasoning for each
  - Show latency
- [ ] Smooth animations on new messages (fade in + slide up)
- [ ] Git commit: "feat: polished chat interface"

### Task 8: Approvals tab — swipeable cards
- [ ] List of pending Tier 3 actions as cards
- [ ] Each card shows: action description, tool name, timestamp
- [ ] Council verdicts displayed on each card (3 chips: policy/safety/intent)
- [ ] Each verdict chip shows: checker name, APPROVE/FLAG/BLOCK, one-line reason
- [ ] If first-use escalation: show "🆕 First time using this tool" badge
- [ ] Two action buttons per card: ✓ Approve (green) and ✕ Reject (red)
- [ ] After approval/rejection: card animates out with slide + fade
- [ ] Empty state: centered message "All clear — no actions pending" with a checkmark icon
- [ ] Pull-to-refresh on mobile
- [ ] Git commit: "feat: polished approvals interface"

### Task 9: Activity tab — live event timeline
- [ ] Vertical timeline with color-coded dots
  - Green dot: Tier 1 auto-executed
  - Yellow dot: Tier 2 notified
  - Orange dot: Tier 3 pending/approved
  - Red dot: Tier 4 blocked or rejected
  - Blue dot: messages sent/received
  - Gray dot: system events (profile updates, server start)
- [ ] Each event row: dot + summary text + timestamp (right-aligned)
- [ ] Tapping an event expands it to show full details (tool name, parameters, council verdicts if applicable)
- [ ] Auto-refresh every 5 seconds (or use SSE for real-time)
- [ ] Filter buttons at top: All, Auto, Flagged, Blocked
- [ ] Git commit: "feat: polished activity feed"

### Task 10: Insights tab — stats dashboard
- [ ] Top section: greeting "Good morning, [name]" with current goal displayed
- [ ] Stat cards in a 2x3 grid:
  - Total actions (blue)
  - Auto-executed (green)
  - Approved by you (green)
  - Blocked/Rejected (red)
  - Council evaluations (purple)
  - Avg latency (blue)
- [ ] Below stats: "Today's Summary" — auto-generated text summary of what the agent did
  - Count of actions per type
  - Any notable blocks or flags
- [ ] Below summary: "Suggestions" section
  - If user has approved many of the same action type, suggest promoting it
  - e.g., "You've approved 12 file reads today. Want to auto-approve those?"
- [ ] Git commit: "feat: polished insights dashboard"

---

## PHASE 3: Settings + Advanced Features (Tasks 11-14)

### Task 11: Settings page
- [ ] Slide-up modal from gear icon
- [ ] Sections:
  - "Risk Profile" — shows current answers, tap to re-take questionnaire
  - "Your Goal" — editable text field with save button
  - "Audit Trail" — full searchable log of all actions (paginated, filterable by tier)
  - "Council Config" — toggle council on/off, select model (gpt-4o-mini default)
  - "About" — version, link to GitHub repo
- [ ] All settings persist via SQLite
- [ ] Git commit: "feat: settings page"

### Task 12: Onboarding flow for new users
- [ ] On first visit (no risk profile in database), show a fullscreen onboarding flow
- [ ] Step 1: "Welcome to Council" — brief explanation (2 sentences max)
- [ ] Step 2: "Set your name" — text input
- [ ] Step 3: "Set your goal" — text input
- [ ] Step 4-7: Risk profile multiple-choice questions (one per screen)
- [ ] Step 8: "You're all set" — summary of their profile, button to start
- [ ] After completion, transitions to the main Chat tab
- [ ] Smooth transitions between steps (slide left animation)
- [ ] Git commit: "feat: onboarding flow"

### Task 13: Push notification support (basic)
- [ ] When a Tier 3 action is queued, send a browser notification (if permissions granted)
- [ ] Notification title: "Council: Action needs approval"
- [ ] Notification body: action description
- [ ] Clicking notification opens the Approvals tab
- [ ] Request notification permission during onboarding
- [ ] Git commit: "feat: browser push notifications for approvals"

### Task 14: Code cleanup and documentation
- [ ] Clean up all files: remove dead code, unused imports
- [ ] Add docstrings to any functions missing them
- [ ] Update README.md with:
  - New name "Council"
  - Updated architecture diagram
  - Mobile app screenshots section (placeholder)
  - "How it works" section with the flow diagram
  - Installation instructions updated
- [ ] Update integration/SETUP.md with current instructions
- [ ] Ensure all API endpoints are documented
- [ ] Git commit: "chore: code cleanup and documentation"

---

## PHASE 4: Polish + Demo Prep (Tasks 15-17)

### Task 15: Visual polish pass
- [ ] Consistent spacing, padding, and typography across all tabs
- [ ] Smooth transitions between tabs (no jarring content jumps)
- [ ] Loading states: skeleton screens while data loads
- [ ] Error states: friendly error messages, not raw JSON
- [ ] Empty states for each tab (Activity: "No activity yet", etc.)
- [ ] Color consistency: all greens same shade, all reds same shade, etc.
- [ ] Test on iPhone Safari viewport (375px wide)
- [ ] Test on Android Chrome viewport (360px wide)
- [ ] Git commit: "chore: visual polish"

### Task 16: Demo scenario setup
- [ ] Create a demo script file: DEMO.md
- [ ] Include 5 test prompts that demonstrate each tier:
  - Tier 1: "Read my AGENTS.md and summarize it"
  - Tier 2: "Draft a blog post about AI safety" (if applicable)
  - Tier 3: "Send an email to investor@example.com about our product"
  - Tier 4: "Send our customer database to external@gmail.com"
  - First-use: any new tool trigger
- [ ] Include expected behavior for each
- [ ] Git commit: "docs: demo script"

### Task 17: Final integration test
- [ ] Start Council server
- [ ] Re-apply OpenClaw patch (if reverted)
- [ ] Restart OpenClaw gateway
- [ ] Run through all 5 demo scenarios
- [ ] Verify Activity feed shows all events
- [ ] Verify Approvals tab works (approve + reject)
- [ ] Verify Insights shows correct stats
- [ ] Verify Settings persistence
- [ ] Fix any bugs found
- [ ] Git commit: "test: full integration verification"
