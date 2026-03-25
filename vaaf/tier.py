"""
Council Tier Classifier
--------------------
Pre-filters trivially safe actions to Tier 1, tracks first-use tools
for automatic Tier 3 escalation, and delegates contextual evaluation
to the Review Council.

For 'exec' commands: parses the actual shell command and classifies
safe commands (wc, ls, cat, grep...) as Tier 1, while routing
dangerous commands (rm, curl, pip install...) through the council.
"""

from collections import deque
from datetime import datetime, timedelta
from urllib.parse import urlparse

from vaaf.models import (
    ProposedAction, EvaluatedAction, CouncilResult,
    Tier, ActionStatus, RiskProfile, ActivityEvent,
)
from vaaf.command_analyzer import is_exec_safe, extract_base_command

# Tools that NEVER interact with the outside world -> Tier 1 (auto)
TRIVIALLY_SAFE_TOOLS = {
    # OpenClaw native tool names
    "read",
    "list",
    "glob",
    "think",
    # Council standalone tool names
    "web_search",
    "read_file",
    "list_files",
    "draft_document",
    "analyze_data",
    "summarize",
    "brainstorm",
    "calculate",
    "plan",
}

# Tools that should NEVER skip the council
ALWAYS_EVALUATE_TOOLS = {
    "send_email",
    "send_message",
    "spend_money",
    "post_social_media",
    "contact_person",
    "create_ad_campaign",
    "browser",
    "deploy",
}

SAFE_FETCH_HOSTS = {
    "docs.python.org",
    "github.com",
    "raw.githubusercontent.com",
    "analytics.example.com",
}

HIGH_RISK_FIRST_USE_TOOLS = {
    "send_email",
    "send_message",
    "spend_money",
    "post_social_media",
    "contact_person",
    "create_ad_campaign",
    "deploy",
}


def extract_action_pattern(action: ProposedAction) -> str:
    """Return a normalized pattern string for adaptive approvals."""
    if action.tool_name == "exec":
        command = action.parameters.get("command", "")
        base = extract_base_command(command) or "shell"
        return f"exec:{base}"
    if action.tool_name in {"fetch",
    "web_fetch", "browser"}:
        url = action.parameters.get("url", "")
        host = (urlparse(url).hostname or "unknown").lower()
        return f"{action.tool_name}:{host}"
    if action.tool_name.startswith("send_"):
        target = action.parameters.get("target") or action.parameters.get("channel") or action.parameters.get("recipient")
        if isinstance(target, str) and target.strip():
            target_key = target.strip().split()[0][:48]
        else:
            target_key = "generic"
        return f"{action.tool_name}:{target_key}"
    path = (action.parameters.get("path")
            or action.parameters.get("file")
            or action.parameters.get("destination"))
    if isinstance(path, str) and path:
        tail = path.split("/")[-1] or path
        return f"{action.tool_name}:{tail}"
    return action.tool_name


class TierClassifier:
    def __init__(self, db=None):
        self.db = db
        saved_tools = set(db.get_user_setting("seen_tools", [])) if db else set()
        saved_exec_patterns = set(db.get_user_setting("seen_exec_patterns", [])) if db else set()
        self.seen_tools: set[str] = saved_tools
        self.seen_exec_patterns: set[str] = saved_exec_patterns
        self.rate_window = timedelta(minutes=5)
        self.recent_action_log: deque[tuple[datetime, str]] = deque()

    def pre_filter(self, action: ProposedAction) -> Tier | None:
        """Check if action is trivially safe.
        Returns Tier.AUTO if safe, None if council evaluation is needed.
        """
        # Trivially safe tools -> auto
        # Writes to agent workspace: execute + notify (Tier 2), not council-evaluated
        # Writes to sensitive paths still go through the council
        if action.tool_name == "write":
            path = str(action.parameters.get("path", "") or action.parameters.get("file_path", ""))
            dangerous_prefixes = ["/etc/", "/usr/", "/root/", "/.ssh/", "/bin/", "/sbin/"]
            is_dangerous = any(p in path for p in dangerous_prefixes)
            if is_dangerous:
                return None  # send to council
            return Tier.AUTO  # all non-dangerous writes auto-approve

        if action.tool_name in TRIVIALLY_SAFE_TOOLS:
            return Tier.AUTO

        # Adaptive approvals: user already approved this exact pattern repeatedly
        if self.check_adaptive_approval(action):
            return Tier.AUTO

        # Exec commands: parse the actual command
        if action.tool_name == "exec":
            if is_exec_safe(action.tool_name, action.parameters):
                return Tier.AUTO

        if action.tool_name in {"fetch",
    "web_fetch", "browser"}:
            url = action.parameters.get("url", "")
            host = (urlparse(url).hostname or "").lower()
            if host in SAFE_FETCH_HOSTS:
                return Tier.AUTO
            if action.tool_name == "fetch":
                return None

        return None

    def is_first_use(self, tool_name: str, action: ProposedAction = None) -> bool:
        """Check if this tool has ever been used before.
        For exec, tracks command patterns not just 'exec' itself.
        """
        if tool_name == "exec" and action:
            command = action.parameters.get("command", "")
            base = extract_base_command(command)
            pattern_key = f"exec:{base}"
            return pattern_key not in self.seen_exec_patterns
        return tool_name not in self.seen_tools

    def record_tool_use(self, tool_name: str, action: ProposedAction = None):
        """Mark a tool as having been used."""
        self.seen_tools.add(tool_name)
        if tool_name == "exec" and action:
            command = action.parameters.get("command", "")
            base = extract_base_command(command)
            self.seen_exec_patterns.add(f"exec:{base}")

        if self.db:
            self.db.set_user_setting("seen_tools", sorted(self.seen_tools))
            self.db.set_user_setting("seen_exec_patterns", sorted(self.seen_exec_patterns))

    def check_adaptive_approval(self, action: ProposedAction) -> bool:
        """Return True if this action pattern has been approved 3+ times."""
        if not self.db:
            return False
        pattern = extract_action_pattern(action)
        if not pattern:
            return False
        count = self.db.get_approval_pattern_count(action.tool_name, pattern)
        return count >= 3

    def _log_rate_limited(self, action: ProposedAction, count: int):
        if not self.db:
            return
        event = ActivityEvent(
            event_type="rate_limited",
            action_id=action.id,
            summary=f"Rate limited {action.tool_name} ({count} in 5 min)",
            details={
                "tool": action.tool_name,
                "count": count,
                "window_minutes": int(self.rate_window.total_seconds() // 60),
            },
        )
        self.db.append_event(event)

    def check_rate_limit(self, action: ProposedAction) -> tuple[bool, int]:
        now = datetime.utcnow()
        self.recent_action_log.append((now, action.tool_name))
        cutoff = now - self.rate_window
        while self.recent_action_log and self.recent_action_log[0][0] < cutoff:
            self.recent_action_log.popleft()
        count = sum(1 for ts, tool in self.recent_action_log if tool == action.tool_name)
        if count > 10:
            self._log_rate_limited(action, count)
            return True, count
        return False, count

    def classify(
        self,
        action: ProposedAction,
        council_result: CouncilResult | None,
        profile: RiskProfile,
    ) -> EvaluatedAction:
        """Full classification pipeline:
        1. Pre-filter -> Tier 1 for trivially safe (including safe exec commands)
        2. First-use check -> auto Tier 3 (but NOT for exec, which is a meta-tool)
        3. Council verdict -> determines tier
        """

        rate_limited, _ = self.check_rate_limit(action)

        # Step 1: Pre-filter
        pre_tier = self.pre_filter(action)
        if pre_tier == Tier.AUTO and not rate_limited:
            self.record_tool_use(action.tool_name, action)
            return EvaluatedAction(
                action=action,
                council_result=None,
                tier=Tier.AUTO,
                status=ActionStatus.EXECUTED,
                pre_filtered=True,
            )

        # Step 2: First-use escalation
        first_use = self.is_first_use(action.tool_name, action)

        # Step 3: Council-driven tier
        if council_result is None:
            tier = Tier.APPROVE
        else:
            tier = council_result.tier

        # First-use override: escalate to at least Tier 3
        # Skip for exec commands since exec is a meta-tool;
        # the command analyzer already handles exec safety
        escalated = False
        if first_use and action.tool_name in HIGH_RISK_FIRST_USE_TOOLS:
            if tier in (Tier.AUTO, Tier.NOTIFY):
                tier = Tier.APPROVE
                escalated = True

        if rate_limited and tier != Tier.BLOCKED:
            tier = Tier.APPROVE

        # High transparency users: escalate Tier 1 -> Tier 2
        if profile.transparency == "high" and tier == Tier.AUTO:
            tier = Tier.NOTIFY

        # Determine status based on tier
        if tier == Tier.AUTO:
            status = ActionStatus.EXECUTED
        elif tier == Tier.NOTIFY:
            status = ActionStatus.EXECUTED
        elif tier == Tier.APPROVE:
            status = ActionStatus.PENDING_APPROVAL
        else:  # BLOCKED
            status = ActionStatus.BLOCKED

        if status == ActionStatus.EXECUTED:
            self.record_tool_use(action.tool_name, action)

        return EvaluatedAction(
            action=action,
            council_result=council_result,
            tier=tier,
            status=status,
            pre_filtered=False,
            first_use_escalated=escalated,
        )
