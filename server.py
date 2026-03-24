"""
Council Server
-----------
FastAPI server that orchestrates the agent, council, tier classifier,
and serves the web UI. Run with: python server.py
"""

import os
import json
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI

from vaaf.models import (
    ActivityEvent, ProposedAction, Tier, ActionStatus,
    RiskProfile,
)
from vaaf.council import evaluate_action
from vaaf.benchmark_runner import run_benchmark, BENCHMARK_RESULTS_PATH
from vaaf.tier import TierClassifier
from vaaf.agent import get_agent_response, extract_proposed_actions, simulate_tool_execution
from vaaf.audit import AuditLog
from vaaf.database import CouncilDatabase
from vaaf.risk_profile import (
    ONBOARDING_QUESTIONS, build_profile, profile_to_context,
)
from vaaf.openclaw_client import OpenClawClient

load_dotenv()

# ── Global state ──────────────────────────────────────────────────────────

client: AsyncOpenAI | None = None
openclaw_client: OpenClawClient | None = None
db = CouncilDatabase("council.db")
tier_classifier = TierClassifier(db=db)
audit_log = AuditLog(db=db)
risk_profile = db.load_risk_profile() or RiskProfile()  # Default conservative
user_goal = db.get_user_setting("user_goal", "Grow my online business and increase customer engagement")
user_name = db.get_user_setting("user_name", "there")
council_enabled = db.get_user_setting("council_enabled", True)
council_model = db.get_user_setting("council_model", "gpt-4o-mini")
chat_history: list[dict] = []  # OpenAI message format


def _map_primary_goal(goal_key: str | None) -> str | None:
    """Map onboarding goal choices to human-readable user goal text."""
    if not goal_key:
        return None

    goal_map = {
        "grow_business": "Grow my business",
        "manage_tasks": "Manage my tasks effectively",
        "research": "Research and learn quickly",
        "content_creation": "Create high-quality content",
        "other": "General productivity and assistance",
    }
    return goal_map.get(goal_key)


def _suggest_profile_questions() -> list[dict]:
    """Generate follow-up profile questions from usage patterns."""
    suggestions: list[dict] = []
    actions = audit_log.actions

    if not actions:
        return [
            {
                "id": "suggest_contact_scope",
                "question": "Should first-time outreach messages always require your approval?",
                "options": ["always", "only_external", "never"],
                "reason": "No usage history yet, so we suggest setting a clear communication boundary.",
            }
        ]

    total_actions = len(actions)
    first_use_count = sum(1 for a in actions if a.first_use_escalated)
    approval_count = sum(1 for a in actions if a.status.value == "pending_approval")

    if first_use_count >= 3:
        suggestions.append({
            "id": "suggest_new_tool_policy",
            "question": "You've had several first-time tool escalations. Should new tools default to extra review?",
            "options": ["yes_strict", "risk_based", "no"],
            "reason": f"{first_use_count} first-use escalations observed.",
        })

    if approval_count >= max(3, total_actions // 3):
        suggestions.append({
            "id": "suggest_approval_threshold",
            "question": "Would you like to tighten approval thresholds for medium-risk actions?",
            "options": ["tighten", "keep_current", "relax"],
            "reason": f"{approval_count} actions currently require approval.",
        })

    tools = {}
    for action in actions[-50:]:
        tools[action.action.tool_name] = tools.get(action.action.tool_name, 0) + 1
    if tools:
        top_tool, top_count = max(tools.items(), key=lambda kv: kv[1])
        if top_count >= 5:
            suggestions.append({
                "id": "suggest_tool_autonomy",
                "question": f"You frequently use {top_tool}. Should low-risk {top_tool} actions be less interruptive?",
                "options": ["yes", "only_read_only", "no"],
                "reason": f"{top_tool} used {top_count} times recently.",
            })

    return suggestions


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, openclaw_client
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-your"):
        print("\n⚠️  WARNING: Set OPENAI_API_KEY in .env file")
        print("   Copy .env.example to .env and add your key\n")
        client = None
    else:
        client = AsyncOpenAI(api_key=api_key)
        print("✓ OpenAI client initialized")

    gateway_token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
    if gateway_token:
        candidate = OpenClawClient(gateway_token=gateway_token)
        health = await candidate.check_health()
        if health["connected"]:
            openclaw_client = candidate
            print("✓ Connected to OpenClaw gateway")
        else:
            await candidate.close()
            openclaw_client = None
            print(f"⚠ OpenClaw gateway unavailable: {health['error']}")
    else:
        openclaw_client = None
        print("⚠ No OPENCLAW_GATEWAY_TOKEN — standalone mode")

    print("✓ Council server ready at http://localhost:8000\n")
    try:
        yield
    finally:
        if openclaw_client:
            await openclaw_client.close()

app = FastAPI(title="Council", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

benchmark_results_path: Path = BENCHMARK_RESULTS_PATH


# ── Request/Response models ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str

class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool

class ProfileAnswers(BaseModel):
    answers: dict  # {question_id: value}

class GoalUpdate(BaseModel):
    goal: str

class SettingsUpdate(BaseModel):
    user_goal: str | None = None
    user_name: str | None = None
    council_enabled: bool | None = None
    council_model: str | None = None

class EvaluateRequest(BaseModel):
    """Incoming tool call from OpenClaw/ClawBands for council evaluation."""
    tool_name: str
    arguments: dict = {}
    description: str = ""
    context: str = ""  # any extra context from the agent


# ── API Routes ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Serve the single-page web application."""
    return FileResponse("static/index.html")


@app.get("/api/onboarding")
async def get_onboarding():
    """Return onboarding questions for risk profile setup."""
    return {"questions": ONBOARDING_QUESTIONS, "current_profile": risk_profile.model_dump()}


@app.post("/api/profile")
async def update_profile(req: ProfileAnswers):
    """Update risk profile from onboarding answers."""
    global risk_profile, user_goal
    risk_profile = build_profile(req.answers)
    db.save_risk_profile(risk_profile)

    primary_goal = _map_primary_goal(req.answers.get("primary_goal"))
    if primary_goal:
        user_goal = primary_goal
        db.set_user_setting("user_goal", user_goal)

    audit_log.log_event(ActivityEvent(
        event_type="profile_updated",
        summary="Risk profile updated",
        details={
            **risk_profile.model_dump(),
            "user_goal": user_goal,
        },
    ))
    return {"profile": risk_profile.model_dump(), "user_goal": user_goal}


@app.post("/api/profile/suggest")
async def suggest_profile_questions():
    """Return adaptive follow-up profile questions from observed usage patterns."""
    return {
        "questions": _suggest_profile_questions(),
        "based_on_actions": len(audit_log.actions),
    }


@app.post("/api/goal")
async def update_goal(req: GoalUpdate):
    """Update the user's stated goal."""
    global user_goal
    user_goal = req.goal
    db.set_user_setting("user_goal", user_goal)
    return {"goal": user_goal}


@app.get("/api/goal")
async def get_goal():
    """Return the current persisted user goal."""
    return {"goal": user_goal}


@app.get("/api/settings")
async def get_settings():
    """Return persisted user settings for UI consumption."""
    return {
        "user_goal": user_goal,
        "user_name": user_name,
        "council_enabled": council_enabled,
        "council_model": council_model,
    }


@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    """Update user settings (goal/name/config) with SQLite persistence."""
    global user_goal, user_name, council_enabled, council_model

    if req.user_goal is not None:
        user_goal = req.user_goal
        db.set_user_setting("user_goal", user_goal)

    if req.user_name is not None:
        user_name = req.user_name
        db.set_user_setting("user_name", user_name)

    if req.council_enabled is not None:
        council_enabled = req.council_enabled
        db.set_user_setting("council_enabled", council_enabled)

    if req.council_model is not None:
        council_model = req.council_model
        db.set_user_setting("council_model", council_model)

    return {
        "user_goal": user_goal,
        "user_name": user_name,
        "council_enabled": council_enabled,
        "council_model": council_model,
    }


@app.get("/api/gateway/status")
async def gateway_status():
    """Return current OpenClaw gateway connectivity status."""
    connected = bool(openclaw_client)
    gateway_url = (
        openclaw_client.gateway_url
        if openclaw_client
        else os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
    )
    return {
        "connected": connected,
        "mode": "openclaw" if connected else "standalone",
        "gateway_url": gateway_url,
    }

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Send a message to the agent. The agent reasons and proposes actions,
    which are intercepted by Council before execution."""
    global chat_history

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

    if not client:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured. Set OPENAI_API_KEY in .env")

    # Log user message
    audit_log.log_event(ActivityEvent(
        event_type="message_received",
        summary=f"User: {req.message[:100]}",
    ))

    # Add to chat history
    chat_history.append({"role": "user", "content": req.message})

    # Get agent response
    response = await get_agent_response(client, chat_history)
    msg = response.choices[0].message

    # Extract text response and proposed actions
    agent_text = msg.content or ""
    proposed_actions = extract_proposed_actions(response)

    # Process each proposed action through Council pipeline
    evaluated_actions = []
    for action in proposed_actions:
        evaluated = await _process_action(action)
        evaluated_actions.append(evaluated)

    # Build response with action results for the agent's context
    tool_results = []
    for ea in evaluated_actions:
        if ea.status == ActionStatus.EXECUTED:
            result = simulate_tool_execution(ea.action)
            ea.execution_result = result
            tool_results.append(f"✓ {ea.action.description} — {result}")
        elif ea.status == ActionStatus.PENDING_APPROVAL:
            tool_results.append(f"⏳ {ea.action.description} — Awaiting your approval")
        elif ea.status == ActionStatus.BLOCKED:
            reason = ""
            if ea.council_result and ea.council_result.votes:
                safety = next((v for v in ea.council_result.votes if v.checker == "safety"), None)
                reason = f": {safety.reason}" if safety else ""
            tool_results.append(f"🚫 {ea.action.description} — Blocked{reason}")

    # Add agent response to chat history
    assistant_content = agent_text
    if tool_results:
        assistant_content += "\n\n**Action Results:**\n" + "\n".join(tool_results)
    chat_history.append({"role": "assistant", "content": assistant_content})

    # Keep chat history manageable
    if len(chat_history) > 30:
        chat_history = chat_history[-20:]

    return {
        "agent_text": agent_text,
        "actions": [_serialize_evaluated(ea) for ea in evaluated_actions],
        "tool_results": tool_results,
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Stream OpenClaw chat responses as SSE tokens."""
    global chat_history

    if not openclaw_client:
        raise HTTPException(status_code=503, detail="Streaming unavailable in standalone mode")

    async def event_stream():
        chunks: list[str] = []
        try:
            async for token in openclaw_client.send_message_stream(req.message, chat_history[-20:]):
                chunks.append(token)
                payload = json.dumps({"token": token})
                yield f"data: {payload}\\n\\n"

            full_text = "".join(chunks).strip()
            if full_text:
                chat_history.append({"role": "user", "content": req.message})
                chat_history.append({"role": "assistant", "content": full_text})
                if len(chat_history) > 30:
                    chat_history[:] = chat_history[-20:]

                audit_log.log_event(ActivityEvent(
                    event_type="message_received",
                    summary=f"User: {req.message[:100]}",
                ))
                audit_log.log_event(ActivityEvent(
                    event_type="message_sent",
                    summary=f"Agent: {full_text[:100]}",
                ))
            yield "data: [DONE]\\n\\n"
        except Exception as exc:
            err_payload = json.dumps({"error": str(exc)[:200]})
            yield f"data: {err_payload}\\n\\n"
            yield "data: [DONE]\\n\\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _process_action(action: ProposedAction):
    """Run an action through the full Council pipeline."""

    # Step 1: Pre-filter check
    pre_tier = tier_classifier.pre_filter(action)

    if not council_enabled:
        evaluated = tier_classifier.classify(action, None, risk_profile)
        if evaluated.status == ActionStatus.EXECUTED:
            evaluated.execution_result = simulate_tool_execution(action)
        audit_log.log_action(evaluated)
        return evaluated

    if pre_tier == Tier.AUTO:
        # Trivially safe — skip council
        evaluated = tier_classifier.classify(action, None, risk_profile)
        result = simulate_tool_execution(action)
        evaluated.execution_result = result
        audit_log.log_action(evaluated)
        return evaluated

    # Step 2: Run through review council
    profile_text = profile_to_context(risk_profile)
    recent = audit_log.get_recent_action_summaries(5)

    council_result = await evaluate_action(
        client=client,
        action_description=action.description,
        action_reasoning=action.reasoning,
        tool_name=action.tool_name,
        parameters=action.parameters,
        risk_profile_text=profile_text,
        user_goal=user_goal,
        recent_actions=recent,
    )

    # Step 3: Classify with council result
    evaluated = tier_classifier.classify(action, council_result, risk_profile)

    # Step 4: Auto-execute if Tier 1 or 2
    if evaluated.status == ActionStatus.EXECUTED:
        result = simulate_tool_execution(action)
        evaluated.execution_result = result

    audit_log.log_action(evaluated)
    return evaluated


@app.post("/api/approve")
async def approve_action(req: ApprovalRequest):
    """Approve or reject a pending action."""
    if req.approved:
        action = audit_log.approve_action(req.action_id)
        if action:
            # Execute the approved action
            result = simulate_tool_execution(action.action)
            action.execution_result = result
            action.status = ActionStatus.EXECUTED
            tier_classifier.record_tool_use(action.action.tool_name)
            return {"status": "approved", "result": result, "action": _serialize_evaluated(action)}
    else:
        action = audit_log.reject_action(req.action_id)
        if action:
            return {"status": "rejected", "action": _serialize_evaluated(action)}

    raise HTTPException(status_code=404, detail="Action not found or not pending")


@app.get("/api/approvals")
async def get_pending_approvals():
    """Get all actions pending approval."""
    pending = audit_log.get_pending_approvals()
    return {"pending": [_serialize_evaluated(a) for a in pending]}


@app.get("/api/activity")
async def get_activity():
    """Get the activity feed (all events)."""
    events = audit_log.events[-50:]  # Last 50
    return {"events": [_serialize_event(e) for e in reversed(events)]}


@app.get("/api/insights")
async def get_insights():
    """Get aggregated stats."""
    stats = audit_log.get_stats()
    return {"stats": stats.model_dump(), "goal": user_goal}


@app.post("/api/benchmark/run")
async def benchmark_run():
    """Execute the full benchmark suite and persist the latest results."""
    if not client:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    results = await run_benchmark(client, tier_classifier, risk_profile, audit_log, user_goal)
    benchmark_results_path.write_text(json.dumps(results, indent=2))
    return {"results": results}


@app.get("/api/benchmark/results")
async def benchmark_results():
    """Return the last saved benchmark results if available."""
    if not benchmark_results_path.exists():
        raise HTTPException(status_code=404, detail="Benchmark has not been run yet")

    try:
        data = json.loads(benchmark_results_path.read_text())
    except json.JSONDecodeError as exc:  # pragma: no cover - corrupted file
        raise HTTPException(status_code=500, detail=f"Benchmark results unreadable: {exc}")
    return {"results": data}


@app.get("/api/actions")
async def get_all_actions():
    """Get all evaluated actions for the audit trail."""
    return {"actions": [_serialize_evaluated(a) for a in reversed(audit_log.actions[-100:])]}


@app.post("/api/evaluate")
async def evaluate_external_action(req: EvaluateRequest):
    """Evaluate a tool call from OpenClaw/ClawBands.
    This is the integration endpoint — external agent runtimes send
    proposed actions here and get back a verdict (allow/block/queue).
    
    Returns:
        decision: "allow" | "block" | "queue"
        tier: the assigned tier
        council: full council verdict with reasoning
        action_id: ID for approval tracking (if queued)
    """
    if not client:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    # Build a description from tool name and arguments if not provided
    desc = req.description or f"{req.tool_name}({json.dumps(req.arguments)[:100]})"

    # Create a ProposedAction from the external request
    action = ProposedAction(
        tool_name=req.tool_name,
        description=desc,
        parameters=req.arguments,
        reasoning=req.context,
    )

    # Run through the full Council pipeline
    evaluated = await _process_action(action)

    # Map status to a simple decision for the caller
    if evaluated.status in (ActionStatus.EXECUTED,):
        decision = "allow"
    elif evaluated.status == ActionStatus.PENDING_APPROVAL:
        decision = "queue"
    elif evaluated.status == ActionStatus.BLOCKED:
        decision = "block"
    else:
        decision = "block"  # default safe

    response = {
        "decision": decision,
        "tier": evaluated.tier.value,
        "action_id": evaluated.action.id,
        "pre_filtered": evaluated.pre_filtered,
        "first_use_escalated": evaluated.first_use_escalated,
    }

    if evaluated.council_result:
        response["council"] = {
            "final_verdict": evaluated.council_result.final_verdict.value,
            "total_latency_ms": evaluated.council_result.total_latency_ms,
            "votes": [
                {
                    "checker": v.checker,
                    "verdict": v.verdict.value,
                    "reason": v.reason,
                    "latency_ms": v.latency_ms,
                }
                for v in evaluated.council_result.votes
            ],
        }

    return response


@app.get("/api/evaluate/{action_id}/status")
async def check_approval_status(action_id: str):
    """Check if a queued action has been approved/rejected.
    OpenClaw polls this while waiting for user approval."""
    for a in audit_log.actions:
        if a.action.id == action_id:
            if a.status == ActionStatus.PENDING_APPROVAL:
                return {"status": "pending"}
            elif a.status in (ActionStatus.APPROVED, ActionStatus.EXECUTED):
                return {"status": "approved"}
            elif a.status == ActionStatus.REJECTED:
                return {"status": "rejected"}
            elif a.status == ActionStatus.BLOCKED:
                return {"status": "blocked"}
    raise HTTPException(status_code=404, detail="Action not found")

# ── Serialization helpers ─────────────────────────────────────────────────

def _serialize_evaluated(ea) -> dict:
    d = {
        "id": ea.action.id,
        "tool_name": ea.action.tool_name,
        "description": ea.action.description,
        "parameters": ea.action.parameters,
        "reasoning": ea.action.reasoning,
        "tier": ea.tier.value,
        "status": ea.status.value,
        "pre_filtered": ea.pre_filtered,
        "first_use_escalated": ea.first_use_escalated,
        "execution_result": ea.execution_result,
        "approved_by": ea.approved_by,
        "timestamp": ea.timestamp.isoformat(),
    }
    if ea.council_result:
        d["council"] = {
            "final_verdict": ea.council_result.final_verdict.value,
            "total_latency_ms": ea.council_result.total_latency_ms,
            "votes": [
                {
                    "checker": v.checker,
                    "verdict": v.verdict.value,
                    "reason": v.reason,
                    "latency_ms": v.latency_ms,
                }
                for v in ea.council_result.votes
            ],
        }
    return d


def _serialize_event(e: ActivityEvent) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "action_id": e.action_id,
        "summary": e.summary,
        "details": e.details,
        "tier": e.tier.value if e.tier else None,
        "timestamp": e.timestamp.isoformat(),
    }


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
