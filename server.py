"""
Council Server
-----------
FastAPI server that orchestrates the agent, council, tier classifier,
and serves the web UI. Run with: python server.py
"""

import os
import json
from datetime import datetime
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI

from vaaf.models import (
    ActivityEvent, ProposedAction, Tier, ActionStatus,
    RiskProfile,
)
from vaaf.council import evaluate_action
from vaaf.tier import TierClassifier
from vaaf.agent import get_agent_response, extract_proposed_actions, simulate_tool_execution
from vaaf.audit import AuditLog
from vaaf.database import CouncilDatabase
from vaaf.risk_profile import (
    ONBOARDING_QUESTIONS, build_profile, profile_to_context,
)

load_dotenv()

# ── Global state ──────────────────────────────────────────────────────────

client: AsyncOpenAI | None = None
db = CouncilDatabase("council.db")
tier_classifier = TierClassifier(db=db)
audit_log = AuditLog(db=db)
risk_profile = db.load_risk_profile() or RiskProfile()  # Default conservative
user_goal = db.get_user_setting("user_goal", "Grow my online business and increase customer engagement")
user_name = db.get_user_setting("user_name", "there")
chat_history: list[dict] = []  # OpenAI message format


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-your"):
        print("\n⚠️  WARNING: Set OPENAI_API_KEY in .env file")
        print("   Copy .env.example to .env and add your key\n")
        client = None
    else:
        client = AsyncOpenAI(api_key=api_key)
        print("✓ OpenAI client initialized")
    print("✓ Council server ready at http://localhost:8000\n")
    yield


app = FastAPI(title="Council", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")


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

class EvaluateRequest(BaseModel):
    """Incoming tool call from OpenClaw/ClawBands for council evaluation."""
    tool_name: str
    arguments: dict = {}
    description: str = ""
    context: str = ""  # any extra context from the agent


# ── API Routes ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/api/onboarding")
async def get_onboarding():
    """Return onboarding questions for risk profile setup."""
    return {"questions": ONBOARDING_QUESTIONS, "current_profile": risk_profile.model_dump()}


@app.post("/api/profile")
async def update_profile(req: ProfileAnswers):
    """Update risk profile from onboarding answers."""
    global risk_profile
    risk_profile = build_profile(req.answers)
    db.save_risk_profile(risk_profile)
    audit_log.log_event(ActivityEvent(
        event_type="profile_updated",
        summary="Risk profile updated",
        details=risk_profile.model_dump(),
    ))
    return {"profile": risk_profile.model_dump()}


@app.post("/api/goal")
async def update_goal(req: GoalUpdate):
    """Update the user's stated goal."""
    global user_goal
    user_goal = req.goal
    db.set_user_setting("user_goal", user_goal)
    return {"goal": user_goal}


@app.get("/api/goal")
async def get_goal():
    return {"goal": user_goal}


@app.get("/api/settings")
async def get_settings():
    """Return persisted user settings for UI consumption."""
    return {"user_goal": user_goal, "user_name": user_name}


@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    """Update user settings (goal/name) with SQLite persistence."""
    global user_goal, user_name

    if req.user_goal is not None:
        user_goal = req.user_goal
        db.set_user_setting("user_goal", user_goal)

    if req.user_name is not None:
        user_name = req.user_name
        db.set_user_setting("user_name", user_name)

    return {"user_goal": user_goal, "user_name": user_name}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Send a message to the agent. The agent reasons and proposes actions,
    which are intercepted by Council before execution."""
    global chat_history

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


async def _process_action(action: ProposedAction):
    """Run an action through the full Council pipeline."""

    # Step 1: Pre-filter check
    pre_tier = tier_classifier.pre_filter(action)

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
