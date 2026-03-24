# Council — OpenClaw Gateway Integration Tasks
# Complete these sequentially. One task per cron invocation.
# After each task: test, commit, push.

## STATUS KEY
# [ ] = not started
# [x] = complete

---

## Task 1: Add OpenClaw gateway client module
- [x] Create the file `vaaf/openclaw_client.py` with the following content:
  - A class `OpenClawClient` that connects to OpenClaw's gateway
  - It uses `httpx.AsyncClient` to POST to `http://127.0.0.1:18789/v1/chat/completions`
  - Constructor takes `gateway_url` (default from env `OPENCLAW_GATEWAY_URL` or `http://127.0.0.1:18789`) and `gateway_token` (from env `OPENCLAW_GATEWAY_TOKEN`)
  - Method `send_message(message: str, history: list[dict]) -> dict` that:
    - Sends `{"model": "openclaw:main", "messages": [...history, {"role":"user","content":message}], "stream": false}` to the API
    - Includes header `Authorization: Bearer {gateway_token}`
    - Returns `{"text": "...", "error": None}` on success
    - Returns `{"text": "", "error": "description"}` on failure (connection error, auth error, etc)
  - Method `check_health() -> dict` that GETs `/health` and returns `{"connected": bool, "error": str|None}`
  - Property `is_configured -> bool` that returns True if gateway_token is set
- [x] Run: `pip install httpx` and add `httpx` to requirements.txt
- [x] Test: `python -c "from vaaf.openclaw_client import OpenClawClient; print('OK')"`
- [x] Git commit: "feat: add OpenClaw gateway client"

## Task 2: Integrate gateway client into server.py
- [x] In server.py, add import: `from vaaf.openclaw_client import OpenClawClient`
- [x] Add global variable: `openclaw_client = None`
- [x] In the lifespan/startup function, after existing initialization, add:
  - Read `OPENCLAW_GATEWAY_TOKEN` from env
  - If token exists, create `OpenClawClient(gateway_token=token)`
  - Call `await openclaw_client.check_health()`
  - If connected, print "✓ Connected to OpenClaw gateway"
  - If not connected, set `openclaw_client = None` and print warning
  - If no token, print "⚠ No OPENCLAW_GATEWAY_TOKEN — standalone mode"
- [x] Add new endpoint `GET /api/gateway/status` that returns:
  - `{"connected": bool, "mode": "openclaw"|"standalone", "gateway_url": str}`
- [x] Test: restart server, verify it prints connection status
- [x] Git commit: "feat: initialize OpenClaw gateway on startup"

## Task 3: Route chat through OpenClaw gateway
- [x] In the `/api/chat` endpoint, add routing at the TOP of the function:
  ```python
  if openclaw_client:
      result = await openclaw_client.send_message(req.message, chat_history[-20:])
      if not result["error"]:
          chat_history.append({"role": "user", "content": req.message})
          chat_history.append({"role": "assistant", "content": result["text"]})
          audit_log.log_event(ActivityEvent(
              event_type="message_received",
              summary=f"User: {req.message[:100]}",
          ))
          audit_log.log_event(ActivityEvent(
              event_type="message_sent",
              summary=f"Agent: {result['text'][:100]}",
          ))
          return {
              "agent_text": result["text"],
              "actions": [],
              "tool_results": [],
              "source": "openclaw",
          }
      # If OpenClaw fails, fall through to standalone agent
  ```
- [x] The existing standalone chat code remains as fallback
- [x] Test: send a message through the UI, verify it reaches OpenClaw (check OpenClaw logs)
- [x] Git commit: "feat: route chat through OpenClaw gateway"

## Task 4: Add OPENCLAW_GATEWAY_TOKEN to .env
- [x] Read the current gateway token: run `openclaw config get gateway.auth.token`
- [x] Add to .env file: `OPENCLAW_GATEWAY_TOKEN=<the token value>`
- [x] Make sure .env is in .gitignore (it should already be)
- [x] Add to .env.example: `OPENCLAW_GATEWAY_TOKEN=your-openclaw-gateway-token`
- [x] Test: restart server, verify "✓ Connected to OpenClaw gateway" appears
- [x] Git commit: "feat: configure gateway token"

## Task 5: Show connection status in the UI
- [x] In static/index.html, add a connection indicator to the top bar:
  - Green dot + "Connected to OpenClaw" when gateway is connected
  - Yellow dot + "Standalone mode" when using standalone agent
- [x] On page load, call `GET /api/gateway/status` and update the indicator
- [x] In the chat input placeholder, show:
  - "Talk to your OpenClaw agent..." when connected
  - "Talk to Council agent..." when standalone
- [x] Poll gateway status every 30 seconds and update indicator
- [x] Git commit: "feat: show gateway connection status in UI"

## Task 6: Improve chat to show OpenClaw's tool usage
- [ ] When OpenClaw responds, its text often contains tool usage info (like "[used tool: exec]" or similar markers)
- [ ] Parse the agent response text for any tool/action references
- [ ] If the Council security patch is active, actions also appear in the Activity tab via /api/evaluate
- [ ] Add a small info banner in chat when connected: "Messages are sent to your OpenClaw agent. Actions are monitored by Council."
- [ ] Make sure long responses render properly (handle markdown-like formatting: bold, code blocks, lists)
- [ ] Add basic markdown rendering for agent responses:
  - **bold** text
  - `code` inline
  - ```code blocks```
  - Line breaks preserved
- [ ] Git commit: "feat: improved chat rendering for OpenClaw responses"

## Task 7: Add streaming support for OpenClaw responses
- [ ] Add a new endpoint `POST /api/chat/stream` that uses SSE (Server-Sent Events)
- [ ] Use OpenClawClient.send_message_stream() to stream tokens
- [ ] In the frontend, when sending a message:
  - Use `fetch` with `EventSource` or `ReadableStream` to read SSE
  - Show tokens appearing one by one in the agent's message bubble
  - Show a typing indicator while streaming
- [ ] Fall back to non-streaming if SSE fails
- [ ] Git commit: "feat: streaming chat responses"

## Task 8: Mobile PWA polish for phone access
- [ ] Ensure manifest.json exists with: name "Council", display "standalone", theme_color "#0a0a0a", background_color "#0a0a0a"
- [ ] Ensure apple-mobile-web-app-capable and apple-mobile-web-app-status-bar-style meta tags are set
- [ ] Bottom nav bar must be fixed at the bottom with safe-area padding: `padding-bottom: env(safe-area-inset-bottom)`
- [ ] Chat input must sit above the bottom nav and above the mobile keyboard when focused
- [ ] Test: the app must be fully usable at 375px viewport width (iPhone SE)
- [ ] No horizontal scrolling anywhere
- [ ] Touch targets (buttons, tabs) must be at least 44px tall
- [ ] Add viewport meta tag: `<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">`
- [ ] Git commit: "feat: mobile PWA polish"

## Task 9: Add ngrok/tunnel deployment helper
- [ ] Create a file `start.sh` that starts everything needed:
  ```bash
  #!/bin/bash
  echo "Starting Council..."
  cd "$(dirname "$0")"
  source venv/bin/activate
  
  # Start the Council server in background
  python -c "import uvicorn; from server import app; uvicorn.run(app, host='0.0.0.0', port=8001)" &
  SERVER_PID=$!
  
  echo "Council server running on http://localhost:8001"
  echo "Server PID: $SERVER_PID"
  echo ""
  echo "To expose publicly: ngrok http 8001"
  echo "Then open the ngrok URL on your phone and Add to Home Screen"
  echo ""
  echo "Press Ctrl+C to stop"
  wait $SERVER_PID
  ```
- [ ] Make it executable: `chmod +x start.sh`
- [ ] Update README with deployment instructions for ngrok
- [ ] Git commit: "feat: start script and deployment docs"

## Task 10: End-to-end test and cleanup
- [ ] Start Council server with `./start.sh`
- [ ] Verify gateway connection status shows "Connected to OpenClaw"
- [ ] Send a message through Council chat, verify OpenClaw responds
- [ ] Send a message through Discord, verify it still works
- [ ] Check Activity tab shows events from both channels
- [ ] Check Insights tab shows correct stats
- [ ] Check Approvals tab works (if security patch is active)
- [ ] Clean up: remove any debug prints, unused code, fix typos
- [ ] Update README.md with:
  - How to connect to OpenClaw
  - How to deploy with ngrok
  - How to add to phone home screen
- [ ] Git commit: "test: end-to-end verification and cleanup"
