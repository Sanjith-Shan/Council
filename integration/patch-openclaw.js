#!/usr/bin/env node

/**
 * VAAF Source Patch for OpenClaw
 * ==============================
 * This script patches OpenClaw's tool execution pipeline to call the
 * VAAF server before every tool execution. This is the most reliable
 * integration method for demos.
 *
 * What it does:
 *   1. Finds OpenClaw's installation directory
 *   2. Locates the tool execution file (pi-tool-definition-adapter or attempt)
 *   3. Injects a VAAF interceptor call before tool.execute()
 *   4. Creates a backup of the original file
 *
 * Usage:
 *   node patch-openclaw.js          # Apply patch
 *   node patch-openclaw.js --revert # Revert to original
 */

import { execSync } from "child_process";
import { readFileSync, writeFileSync, existsSync, copyFileSync } from "fs";
import { join, dirname } from "path";

const VAAF_SERVER = process.env.VAAF_SERVER || "http://localhost:8000";

// ── Find OpenClaw installation ──

function findOpenClawDir() {
  // Check common locations
  const candidates = [
    // npm global install
    execSync("npm root -g", { encoding: "utf8" }).trim() + "/openclaw",
    // Local node_modules
    join(process.cwd(), "node_modules/openclaw"),
    // Common manual install locations
    join(process.env.HOME || "~", ".openclaw/node_modules/openclaw"),
    join(process.env.HOME || "~", "openclaw"),
  ];

  for (const dir of candidates) {
    if (existsSync(dir)) {
      console.log(`[VAAF] Found OpenClaw at: ${dir}`);
      return dir;
    }
  }

  console.error("[VAAF] ❌ Could not find OpenClaw installation");
  console.error("[VAAF]   Tried:", candidates.join("\n         "));
  console.error("[VAAF]   Make sure OpenClaw is installed: npm install -g openclaw");
  process.exit(1);
}

// ── The VAAF interceptor code to inject ──

const VAAF_INTERCEPTOR_CODE = `
// ═══ VAAF INTERCEPTOR — START ═══
// Injected by VAAF (Verifiable Agent Autonomy Framework)
// This block calls the VAAF council before every tool execution.
const VAAF_SERVER_URL = "${VAAF_SERVER}";

async function __vaaf_evaluate(toolName, params) {
  try {
    const desc = toolName + "(" + JSON.stringify(params || {}).slice(0, 200) + ")";
    const res = await fetch(VAAF_SERVER_URL + "/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tool_name: toolName,
        arguments: params || {},
        description: desc,
        context: "",
      }),
    });
    if (!res.ok) {
      console.error("[VAAF] Server error " + res.status + ", blocking action");
      return { decision: "block" };
    }
    const data = await res.json();
    
    // Log verdict
    if (data.council) {
      for (const v of data.council.votes) {
        const icon = v.verdict === "APPROVE" ? "✅" : v.verdict === "FLAG" ? "⚠️" : "🚫";
        console.log("[VAAF] " + icon + " " + v.checker + ": " + v.verdict + " — " + v.reason);
      }
    }
    
    if (data.decision === "allow") {
      console.log("[VAAF] ✅ ALLOWED: " + desc);
      return data;
    } else if (data.decision === "queue") {
      console.log("[VAAF] ⏳ QUEUED for approval: " + desc);
      // Poll for approval
      const startTime = Date.now();
      while (Date.now() - startTime < 300000) {
        await new Promise(r => setTimeout(r, 1000));
        try {
          const pollRes = await fetch(VAAF_SERVER_URL + "/api/evaluate/" + data.action_id + "/status");
          const pollData = await pollRes.json();
          if (pollData.status === "approved") { console.log("[VAAF] ✅ Approved by user"); return { decision: "allow" }; }
          if (pollData.status === "rejected") { console.log("[VAAF] ❌ Rejected by user"); return { decision: "block" }; }
          if (pollData.status === "blocked") { return { decision: "block" }; }
        } catch (e) { /* continue polling */ }
      }
      console.log("[VAAF] ⏰ Approval timed out, blocking");
      return { decision: "block" };
    } else {
      console.log("[VAAF] 🚫 BLOCKED: " + desc);
      return data;
    }
  } catch (e) {
    console.error("[VAAF] ❌ Error contacting server: " + e.message);
    return { decision: "block" };
  }
}
// ═══ VAAF INTERCEPTOR — END ═══
`;

const VAAF_GUARD_CODE = `
    // ═══ VAAF GUARD — START ═══
    const __vaaf_result = await __vaaf_evaluate(toolCall.name || toolName, validatedArgs || params);
    if (__vaaf_result.decision === "block") {
      return { type: "tool_result", tool_use_id: toolCall.id || toolCallId, content: "[VAAF] Action blocked by security council" };
    }
    // ═══ VAAF GUARD — END ═══
`;

// ── Patching logic ──

function findToolExecutionFile(openclawDir) {
  // Check possible locations for the tool execution logic
  const candidates = [
    "dist/agents/pi-tool-definition-adapter.js",
    "dist/agents/pi-embedded-runner/run/attempt.js",
    "dist/agents/pi-embedded-runner/run.js",
    "src/agents/pi-tool-definition-adapter.ts",
    "src/agents/pi-embedded-runner/run/attempt.ts",
  ];

  for (const rel of candidates) {
    const full = join(openclawDir, rel);
    if (existsSync(full)) {
      const content = readFileSync(full, "utf8");
      // Look for tool execution patterns
      if (
        content.includes("tool.execute") ||
        content.includes("execute(toolCall") ||
        content.includes("executeTool")
      ) {
        console.log(`[VAAF] Found tool execution in: ${rel}`);
        return full;
      }
    }
  }

  // Broader search in dist/
  const distDir = join(openclawDir, "dist");
  if (existsSync(distDir)) {
    const find = execSync(`grep -rl "tool.execute\\|executeTool\\|execute(toolCall" "${distDir}" --include="*.js" 2>/dev/null || echo ""`, {
      encoding: "utf8",
    }).trim();
    if (find) {
      const firstMatch = find.split("\n")[0];
      console.log(`[VAAF] Found tool execution via grep: ${firstMatch}`);
      return firstMatch;
    }
  }

  console.error("[VAAF] ❌ Could not find tool execution file");
  console.error("[VAAF]   OpenClaw's internal structure may have changed");
  console.error("[VAAF]   Use the plugin method instead (see SETUP.md)");
  process.exit(1);
}

function applyPatch(filePath) {
  const content = readFileSync(filePath, "utf8");

  // Check if already patched
  if (content.includes("VAAF INTERCEPTOR")) {
    console.log("[VAAF] ⚠ File already patched. Use --revert first to re-patch.");
    return;
  }

  // Create backup
  const backupPath = filePath + ".vaaf-backup";
  copyFileSync(filePath, backupPath);
  console.log(`[VAAF] Backup created: ${backupPath}`);

  // Strategy: inject the interceptor function at the top of the file,
  // then inject the guard call before tool.execute() invocations
  let patched = VAAF_INTERCEPTOR_CODE + "\n" + content;

  // Find and inject guard before common execution patterns
  const patterns = [
    // Pattern: result = await tool.execute(...)
    /(const\s+\w+\s*=\s*await\s+tool\.execute\()/g,
    // Pattern: await tool.execute(...)
    /(await\s+tool\.execute\()/g,
    // Pattern: result = await executeTool(...)
    /(const\s+\w+\s*=\s*await\s+executeTool\()/g,
  ];

  let injected = false;
  for (const pattern of patterns) {
    if (pattern.test(patched)) {
      patched = patched.replace(pattern, VAAF_GUARD_CODE + "\n    $1");
      injected = true;
      break; // Only inject once
    }
  }

  if (!injected) {
    console.warn("[VAAF] ⚠ Could not find exact injection point");
    console.warn("[VAAF]   Interceptor function added but guard not injected");
    console.warn("[VAAF]   You may need to manually add the guard — see SETUP.md");
  }

  writeFileSync(filePath, patched);
  console.log(`[VAAF] ✅ Patch applied to: ${filePath}`);
}

function revertPatch(filePath) {
  const backupPath = filePath + ".vaaf-backup";
  if (!existsSync(backupPath)) {
    console.error("[VAAF] ❌ No backup found. Cannot revert.");
    return;
  }
  copyFileSync(backupPath, filePath);
  console.log(`[VAAF] ✅ Reverted to original: ${filePath}`);
}

// ── Main ──

const args = process.argv.slice(2);
const revert = args.includes("--revert");

const openclawDir = findOpenClawDir();
const targetFile = findToolExecutionFile(openclawDir);

if (revert) {
  revertPatch(targetFile);
} else {
  applyPatch(targetFile);
  console.log("\n[VAAF] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("[VAAF] Patch applied successfully!");
  console.log("[VAAF] ");
  console.log("[VAAF] Make sure the VAAF server is running:");
  console.log("[VAAF]   cd vaaf && python server.py");
  console.log("[VAAF] ");
  console.log("[VAAF] Then restart OpenClaw:");
  console.log("[VAAF]   openclaw restart");
  console.log("[VAAF] ");
  console.log("[VAAF] Open http://localhost:8000 to see the dashboard");
  console.log("[VAAF] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
}
