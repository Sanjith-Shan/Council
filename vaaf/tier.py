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

from vaaf.models import (
    ProposedAction, EvaluatedAction, CouncilResult,
    Tier, ActionStatus, RiskProfile,
)
from vaaf.command_analyzer import is_exec_safe, extract_base_command

# Tools that NEVER interact with the outside world -> Tier 1 (auto)
TRIVIALLY_SAFE_TOOLS = {
    # OpenClaw native tool names
    "read",
    "list",
    "glob",
    "think",
    "fetch",
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


class TierClassifier:
    def __init__(self, db=None):
        self.db = db
        saved_tools = set(db.get_user_setting("seen_tools", [])) if db else set()
        saved_exec_patterns = set(db.get_user_setting("seen_exec_patterns", [])) if db else set()
        self.seen_tools: set[str] = saved_tools
        self.seen_exec_patterns: set[str] = saved_exec_patterns

    def pre_filter(self, action: ProposedAction) -> Tier | None:
        """Check if action is trivially safe.
        Returns Tier.AUTO if safe, None if council evaluation is needed.
        """
        # Trivially safe tools -> auto
        if action.tool_name in TRIVIALLY_SAFE_TOOLS:
            return Tier.AUTO

        # Exec commands: parse the actual command
        if action.tool_name == "exec":
            if is_exec_safe(action.tool_name, action.parameters):
                return Tier.AUTO

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

        # Step 1: Pre-filter
        pre_tier = self.pre_filter(action)
        if pre_tier == Tier.AUTO:
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
        if first_use and action.tool_name != "exec":
            if tier in (Tier.AUTO, Tier.NOTIFY):
                tier = Tier.APPROVE
                escalated = True

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
