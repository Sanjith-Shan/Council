from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime
import uuid


class Tier(str, Enum):
    AUTO = "tier1_auto"
    NOTIFY = "tier2_notify"
    APPROVE = "tier3_approve"
    BLOCKED = "tier4_blocked"


class Verdict(str, Enum):
    APPROVE = "APPROVE"
    FLAG = "FLAG"
    BLOCK = "BLOCK"


class ActionStatus(str, Enum):
    PENDING_COUNCIL = "pending_council"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"
    BLOCKED = "blocked"


# ---------- Council ----------

class CouncilVote(BaseModel):
    checker: str  # "policy", "safety", or "intent"
    verdict: Verdict
    reason: str
    latency_ms: float = 0


class CouncilResult(BaseModel):
    votes: list[CouncilVote]
    final_verdict: Verdict
    tier: Tier
    total_latency_ms: float = 0


# ---------- Actions ----------

class ProposedAction(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    tool_name: str
    description: str
    parameters: dict = {}
    reasoning: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EvaluatedAction(BaseModel):
    action: ProposedAction
    council_result: Optional[CouncilResult] = None
    tier: Tier
    status: ActionStatus
    pre_filtered: bool = False
    first_use_escalated: bool = False
    execution_result: Optional[str] = None
    approved_by: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------- Risk Profile ----------

class RiskProfile(BaseModel):
    financial_autonomy: str = "conservative"   # conservative, moderate, aggressive
    communication_autonomy: str = "moderate"   # conservative, moderate, aggressive
    transparency: str = "moderate"             # high, moderate, low
    novelty_tolerance: str = "conservative"    # conservative, moderate, aggressive
    raw_answers: dict = {}


# ---------- Events (Activity Feed) ----------

class ActivityEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    event_type: str  # "action_proposed", "council_evaluated", "tier_assigned", "approved", "rejected", "executed", "blocked", "message_sent", "message_received"
    action_id: Optional[str] = None
    summary: str
    details: dict = {}
    tier: Optional[Tier] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------- Stats ----------

class InsightsStats(BaseModel):
    total_actions: int = 0
    auto_executed: int = 0
    notified: int = 0
    approved: int = 0
    rejected: int = 0
    blocked: int = 0
    pending_approval: int = 0
    council_evaluations: int = 0
    avg_council_latency_ms: float = 0
    first_use_escalations: int = 0
