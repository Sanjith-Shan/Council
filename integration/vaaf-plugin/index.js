/**
 * VAAF Plugin for OpenClaw
 * ========================
 * Intercepts every tool call OpenClaw makes, sends it to the VAAF
 * Review Council for evaluation, and allows/blocks/queues based on the verdict.
 *
 * Uses ClawBands' interception pattern (before_tool_call hook).
 * Falls back to exec approval patching if hooks aren't available.
 */

const VAAF_SERVER = process.env.VAAF_SERVER || "http://localhost:8000";
const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 300000; // 5 min max wait for approval

/**
 * Call the VAAF server to evaluate a tool call.
 * Returns: { decision: "allow"|"block"|"queue", tier, council, action_id }
 */
async function evaluateWithVAAF(toolName, args, description) {
  const response = await fetch(`${VAAF_SERVER}/api/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tool_name: toolName,
      arguments: args || {},
      description: description || `${toolName}(${JSON.stringify(args).slice(0, 200)})`,
      context: "",
    }),
  });

  if (!response.ok) {
    console.error(`[VAAF] Server returned ${response.status}`);
    // Fail-safe: block on server error
    return { decision: "block", reason: "VAAF server unavailable" };
  }

  return await response.json();
}

/**
 * Poll the VAAF server until a queued action is approved or rejected.
 */
async function waitForApproval(actionId) {
  const start = Date.now();

  while (Date.now() - start < POLL_TIMEOUT_MS) {
    try {
      const response = await fetch(
        `${VAAF_SERVER}/api/evaluate/${actionId}/status`
      );
      const data = await response.json();

      if (data.status === "approved") return true;
      if (data.status === "rejected") return false;
      if (data.status === "blocked") return false;
      // still pending — wait and poll again
    } catch (e) {
      console.error(`[VAAF] Poll error: ${e.message}`);
    }

    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }

  console.warn(`[VAAF] Approval timed out for action ${actionId}`);
  return false; // timeout = deny
}

/**
 * Build a human-readable description of a tool call.
 */
function describeToolCall(toolName, args) {
  const a = args || {};
  switch (toolName) {
    case "exec":
    case "process":
    case "bash":
      return `Run command: ${a.command || a.cmd || JSON.stringify(a).slice(0, 100)}`;
    case "write":
    case "create_file":
      return `Write file: ${a.path || a.file_path || "unknown"}`;
    case "edit":
      return `Edit file: ${a.path || a.file_path || "unknown"}`;
    case "read":
      return `Read file: ${a.path || a.file_path || "unknown"}`;
    case "browser":
    case "web_search":
      return `Browser: ${a.url || a.query || a.action || "navigate"}`;
    case "send_message":
      return `Send message to ${a.channel || a.to || "unknown"}: ${(a.text || a.content || "").slice(0, 60)}`;
    default:
      return `${toolName}: ${JSON.stringify(a).slice(0, 120)}`;
  }
}

/**
 * The main interception handler.
 * This function is called BEFORE every tool execution.
 * Returns: { allow: boolean, reason: string }
 */
async function interceptToolCall(toolName, toolCallId, params) {
  const description = describeToolCall(toolName, params);

  console.log(`\n[VAAF] ━━━ Evaluating: ${description}`);

  try {
    const result = await evaluateWithVAAF(toolName, params, description);

    // Log the council's verdicts
    if (result.council) {
      for (const vote of result.council.votes) {
        const icon =
          vote.verdict === "APPROVE" ? "✅" :
          vote.verdict === "FLAG" ? "⚠️" : "🚫";
        console.log(`[VAAF]   ${icon} ${vote.checker}: ${vote.verdict} — ${vote.reason}`);
      }
      console.log(`[VAAF]   ⏱  Council latency: ${result.council.total_latency_ms}ms`);
    }

    if (result.decision === "allow") {
      console.log(`[VAAF] ✅ ALLOWED (${result.tier})`);
      return { allow: true, reason: "Council approved" };
    }

    if (result.decision === "block") {
      console.log(`[VAAF] 🚫 BLOCKED (${result.tier})`);
      return { allow: false, reason: "Council blocked: safety risk" };
    }

    if (result.decision === "queue") {
      console.log(`[VAAF] ⏳ QUEUED for approval (${result.tier})`);
      if (result.first_use_escalated) {
        console.log(`[VAAF]   🆕 First use of tool "${toolName}" — auto-escalated`);
      }
      console.log(`[VAAF]   Waiting for user approval at ${VAAF_SERVER} ...`);

      const approved = await waitForApproval(result.action_id);

      if (approved) {
        console.log(`[VAAF] ✅ User APPROVED`);
        return { allow: true, reason: "User approved" };
      } else {
        console.log(`[VAAF] ❌ User REJECTED`);
        return { allow: false, reason: "User rejected" };
      }
    }

    // Unknown decision — fail safe
    return { allow: false, reason: "Unknown VAAF decision" };

  } catch (e) {
    console.error(`[VAAF] ❌ Error: ${e.message}`);
    // Fail-safe: block if VAAF server is unreachable
    return { allow: false, reason: `VAAF error: ${e.message}` };
  }
}


// ══════════════════════════════════════════════════════════════════════════
// INTEGRATION METHODS — choose one based on your OpenClaw setup
// ══════════════════════════════════════════════════════════════════════════

/**
 * METHOD 1: ClawBands-style hook registration (recommended)
 * Works if ClawBands is installed or if before_tool_call is wired up.
 */
function registerViaHook(api) {
  api.on("before_tool_call", async (event) => {
    const { toolName, toolCallId, params } = event;
    const result = await interceptToolCall(toolName, toolCallId, params);
    if (!result.allow) {
      event.block(result.reason);
    }
  });
  console.log("[VAAF] ✓ Registered via before_tool_call hook");
}

/**
 * METHOD 2: OpenClaw Plugin SDK registration
 * Standard plugin pattern for OpenClaw.
 */
const vaafPlugin = {
  id: "vaaf",
  name: "VAAF — Verifiable Agent Autonomy Framework",
  register(api) {
    console.log("[VAAF] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    console.log("[VAAF] Verifiable Agent Autonomy Framework");
    console.log(`[VAAF] Council server: ${VAAF_SERVER}`);
    console.log("[VAAF] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // Try hook registration first
    if (api.on && typeof api.on === "function") {
      registerViaHook(api);
    } else {
      console.warn("[VAAF] ⚠ before_tool_call hook not available");
      console.warn("[VAAF]   Use Method 3 (source patch) or install ClawBands");
    }

    // Register a tool so the agent can check VAAF status
    api.registerTool("vaaf_status", {
      description: "Check the VAAF security system status and recent evaluations",
      parameters: {},
      handler: async () => {
        try {
          const res = await fetch(`${VAAF_SERVER}/api/insights`);
          const data = await res.json();
          return JSON.stringify(data, null, 2);
        } catch (e) {
          return `VAAF server unreachable: ${e.message}`;
        }
      },
    });
  },
};

export default vaafPlugin;
export { interceptToolCall, evaluateWithVAAF, waitForApproval };
