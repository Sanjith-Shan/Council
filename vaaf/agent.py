"""
VAAF Primary Agent
------------------
The main LLM agent that reasons freely and proposes actions.
Uses OpenAI function calling to propose tool invocations.
Each proposed tool call is intercepted by VAAF before execution.
"""

import json
from openai import AsyncOpenAI
from vaaf.models import ProposedAction


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to someone",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_document",
            "description": "Draft a document (does not send or publish)",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spend_money",
            "description": "Make a purchase or payment",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Amount in USD"},
                    "purpose": {"type": "string"},
                    "vendor": {"type": "string"},
                },
                "required": ["amount", "purpose"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_social_media",
            "description": "Post content to social media",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["platform", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contact_person",
            "description": "Reach out to a new person (not existing contact)",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "channel": {"type": "string", "description": "email, phone, linkedin, etc."},
                    "message": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "channel", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a local file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create or write a file locally",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_data",
            "description": "Analyze data or metrics locally",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_source": {"type": "string"},
                    "analysis_type": {"type": "string"},
                },
                "required": ["data_source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ad_campaign",
            "description": "Create an advertising campaign on a platform",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "budget": {"type": "number"},
                    "target_audience": {"type": "string"},
                    "ad_content": {"type": "string"},
                },
                "required": ["platform", "budget", "ad_content"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are a personal AI business agent. You help the user manage and grow their business by taking actions on their behalf.

You can research, draft content, send emails, post on social media, manage contacts, spend money on marketing, and more. When the user gives you a task, you should reason about the best approach and then propose specific actions by calling the available tools.

Always explain your reasoning before proposing an action. Think about what would genuinely help the user, and propose the most effective approach.

You are free to think creatively — propose novel strategies, discover new opportunities, and suggest actions the user might not have considered. Your thinking is unrestricted. The safety review system will evaluate each proposed action before execution, so feel free to be ambitious in your proposals.

When a tool call is executed, you'll get a result back. When it's pending approval, you'll be told it's awaiting user approval. When blocked, you'll be told why and should adjust your approach."""


TOOL_DESCRIPTIONS = {
    "web_search": "Search the web",
    "send_email": "Send an email",
    "draft_document": "Draft a document (local only)",
    "spend_money": "Make a purchase/payment",
    "post_social_media": "Post to social media",
    "contact_person": "Reach out to a new person",
    "read_file": "Read a local file",
    "create_file": "Create/write a local file",
    "analyze_data": "Analyze data locally",
    "create_ad_campaign": "Create an ad campaign",
}


async def get_agent_response(
    client: AsyncOpenAI,
    messages: list[dict],
    model: str = "gpt-4o-mini",
) -> dict:
    """Get a response from the primary agent.
    Returns the full response object with potential tool calls.
    """
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": AGENT_SYSTEM_PROMPT}] + messages,
        tools=AGENT_TOOLS,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=1000,
    )
    return response


def extract_proposed_actions(response) -> list[ProposedAction]:
    """Extract proposed actions from the agent's tool calls."""
    actions = []
    msg = response.choices[0].message

    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                params = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                params = {}

            desc = TOOL_DESCRIPTIONS.get(tc.function.name, tc.function.name)
            # Build a human-readable description
            if tc.function.name == "send_email":
                desc = f"Send email to {params.get('to', '?')}: {params.get('subject', '')}"
            elif tc.function.name == "spend_money":
                desc = f"Spend ${params.get('amount', '?')} on {params.get('purpose', '?')}"
            elif tc.function.name == "post_social_media":
                desc = f"Post to {params.get('platform', '?')}: {params.get('content', '')[:60]}..."
            elif tc.function.name == "contact_person":
                desc = f"Contact {params.get('name', '?')} via {params.get('channel', '?')}"
            elif tc.function.name == "web_search":
                desc = f"Search: {params.get('query', '?')}"
            elif tc.function.name == "create_ad_campaign":
                desc = f"Create {params.get('platform', '?')} ad campaign (${params.get('budget', '?')})"
            elif tc.function.name == "draft_document":
                desc = f"Draft: {params.get('title', '?')}"

            actions.append(ProposedAction(
                tool_name=tc.function.name,
                description=desc,
                parameters=params,
                reasoning=msg.content or "",
            ))

    return actions


def simulate_tool_execution(action: ProposedAction) -> str:
    """Simulate executing a tool and return a result string.
    In production, this would actually call the tool/API.
    """
    name = action.tool_name
    params = action.parameters

    if name == "web_search":
        return f"Search results for '{params.get('query', '')}': Found 10 relevant results including market analysis, competitor info, and industry trends."
    elif name == "send_email":
        return f"Email sent to {params.get('to', '')} with subject '{params.get('subject', '')}'."
    elif name == "draft_document":
        return f"Document '{params.get('title', '')}' drafted successfully ({len(params.get('content', ''))} chars)."
    elif name == "spend_money":
        return f"Payment of ${params.get('amount', 0)} processed for {params.get('purpose', '')}."
    elif name == "post_social_media":
        return f"Posted to {params.get('platform', '')}: content published successfully."
    elif name == "contact_person":
        return f"Message sent to {params.get('name', '')} via {params.get('channel', '')}."
    elif name == "read_file":
        return f"File '{params.get('path', '')}' read successfully (1,234 bytes)."
    elif name == "create_file":
        return f"File '{params.get('path', '')}' created successfully."
    elif name == "analyze_data":
        return f"Analysis of '{params.get('data_source', '')}' complete: key trends identified."
    elif name == "create_ad_campaign":
        return f"Ad campaign created on {params.get('platform', '')} with ${params.get('budget', 0)} budget."
    else:
        return f"Tool '{name}' executed successfully."
