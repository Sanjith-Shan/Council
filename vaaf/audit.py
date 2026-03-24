"""
Council Audit Logger
-----------------
SQLite-backed event and action audit store.
"""

from vaaf.models import (
    ActivityEvent, EvaluatedAction, InsightsStats,
    Tier, ActionStatus,
)


class AuditLog:
    def __init__(self, db):
        self.db = db

    def log_event(self, event: ActivityEvent):
        self.db.append_event(event)

    def log_action(self, evaluated: EvaluatedAction):
        self.db.upsert_action(evaluated)
        self.log_event(ActivityEvent(
            event_type="action_evaluated",
            action_id=evaluated.action.id,
            summary=f"[{evaluated.tier.value}] {evaluated.action.description}",
            tier=evaluated.tier,
            details={
                "tool": evaluated.action.tool_name,
                "status": evaluated.status.value,
                "pre_filtered": evaluated.pre_filtered,
                "first_use_escalated": evaluated.first_use_escalated,
                "council_votes": [
                    {"checker": v.checker, "verdict": v.verdict.value, "reason": v.reason}
                    for v in (evaluated.council_result.votes if evaluated.council_result else [])
                ],
            },
        ))

    @property
    def events(self) -> list[ActivityEvent]:
        return self.db.list_events()

    @property
    def actions(self) -> list[EvaluatedAction]:
        return self.db.list_actions()

    def get_pending_approvals(self) -> list[EvaluatedAction]:
        return [a for a in self.actions if a.status == ActionStatus.PENDING_APPROVAL]

    def approve_action(self, action_id: str) -> EvaluatedAction | None:
        a = self.db.get_action(action_id)
        if not a or a.status != ActionStatus.PENDING_APPROVAL:
            return None

        a.status = ActionStatus.APPROVED
        a.approved_by = "user"
        self.db.upsert_action(a)
        self.log_event(ActivityEvent(
            event_type="action_approved",
            action_id=action_id,
            summary=f"User approved: {a.action.description}",
            tier=a.tier,
        ))
        return a

    def reject_action(self, action_id: str) -> EvaluatedAction | None:
        a = self.db.get_action(action_id)
        if not a or a.status != ActionStatus.PENDING_APPROVAL:
            return None

        a.status = ActionStatus.REJECTED
        self.db.upsert_action(a)
        self.log_event(ActivityEvent(
            event_type="action_rejected",
            action_id=action_id,
            summary=f"User rejected: {a.action.description}",
            tier=a.tier,
        ))
        return a

    def get_stats(self) -> InsightsStats:
        actions = self.actions
        total = len(actions)
        council_evals = [a for a in actions if a.council_result]
        latencies = [a.council_result.total_latency_ms for a in council_evals if a.council_result]

        return InsightsStats(
            total_actions=total,
            auto_executed=sum(1 for a in actions if a.tier == Tier.AUTO),
            notified=sum(1 for a in actions if a.tier == Tier.NOTIFY),
            approved=sum(1 for a in actions if a.status == ActionStatus.APPROVED),
            rejected=sum(1 for a in actions if a.status == ActionStatus.REJECTED),
            blocked=sum(1 for a in actions if a.status == ActionStatus.BLOCKED),
            pending_approval=sum(1 for a in actions if a.status == ActionStatus.PENDING_APPROVAL),
            council_evaluations=len(council_evals),
            avg_council_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0,
            first_use_escalations=sum(1 for a in actions if a.first_use_escalated),
        )

    def get_recent_action_summaries(self, n: int = 5) -> list[str]:
        return [a.action.description for a in self.actions[-n:]]
