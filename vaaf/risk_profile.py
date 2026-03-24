from vaaf.models import RiskProfile

ONBOARDING_QUESTIONS = [
    {
        "id": "financial_autonomy",
        "question": "How comfortable are you with the agent spending money on your behalf?",
        "options": [
            {"key": "a", "label": "Not at all — always ask me first", "value": "conservative"},
            {"key": "b", "label": "Small routine amounts are fine, ask for anything unusual", "value": "moderate"},
            {"key": "c", "label": "I trust it for regular business expenses, flag only unusual ones", "value": "aggressive"},
        ],
    },
    {
        "id": "communication_autonomy",
        "question": "How should the agent handle contacting new people not in your existing contacts?",
        "options": [
            {"key": "a", "label": "Never contact anyone new without my explicit approval", "value": "conservative"},
            {"key": "b", "label": "It can reach out to potential customers, but I approve the message first", "value": "moderate"},
            {"key": "c", "label": "It can contact anyone relevant to my business goals", "value": "aggressive"},
        ],
    },
    {
        "id": "transparency",
        "question": "What level of transparency do you want for day-to-day operations?",
        "options": [
            {"key": "a", "label": "Notify me of every single action", "value": "high"},
            {"key": "b", "label": "Notify me of important actions, log everything else", "value": "moderate"},
            {"key": "c", "label": "Only notify me when approval is needed", "value": "low"},
        ],
    },
    {
        "id": "novelty_tolerance",
        "question": "How should the agent handle actions it hasn't taken before?",
        "options": [
            {"key": "a", "label": "Always ask me first — I want to approve anything new", "value": "conservative"},
            {"key": "b", "label": "Evaluate the risk and ask me if it seems significant", "value": "moderate"},
            {"key": "c", "label": "Try it and let me know how it went", "value": "aggressive"},
        ],
    },
    {
        "id": "primary_goal",
        "question": "What is your primary goal?",
        "options": [
            {"key": "a", "label": "Grow business", "value": "grow_business"},
            {"key": "b", "label": "Manage tasks", "value": "manage_tasks"},
            {"key": "c", "label": "Research", "value": "research"},
            {"key": "d", "label": "Content creation", "value": "content_creation"},
            {"key": "e", "label": "Other", "value": "other"},
        ],
    },
    {
        "id": "new_tool_discovery",
        "question": "How do you feel about the agent using new tools it discovers?",
        "options": [
            {"key": "a", "label": "Conservative", "value": "conservative"},
            {"key": "b", "label": "Moderate", "value": "moderate"},
            {"key": "c", "label": "Aggressive", "value": "aggressive"},
        ],
    },
]


def build_profile(answers: dict) -> RiskProfile:
    """Build a RiskProfile from onboarding answers.
    answers: {question_id: selected_value} e.g. {"financial_autonomy": "conservative"}
    """
    return RiskProfile(
        financial_autonomy=answers.get("financial_autonomy", "conservative"),
        communication_autonomy=answers.get("communication_autonomy", "moderate"),
        transparency=answers.get("transparency", "moderate"),
        novelty_tolerance=answers.get("novelty_tolerance", "conservative"),
        raw_answers=answers,
    )


def profile_to_context(profile: RiskProfile) -> str:
    """Convert a risk profile to a natural-language summary for the council."""
    lines = [
        "USER RISK PROFILE:",
        f"- Financial autonomy: {profile.financial_autonomy} (the user is {profile.financial_autonomy} about the agent spending money)",
        f"- Communication autonomy: {profile.communication_autonomy} (the user is {profile.communication_autonomy} about the agent contacting people)",
        f"- Transparency preference: {profile.transparency} (the user wants {profile.transparency} visibility into actions)",
        f"- Novelty tolerance: {profile.novelty_tolerance} (the user is {profile.novelty_tolerance} about the agent trying new things)",
    ]
    return "\n".join(lines)
