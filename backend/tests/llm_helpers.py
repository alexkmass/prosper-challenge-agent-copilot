"""
Shared helpers for the LLM eval tests — they exercise the exact tool schema
Pipecat would send at runtime (via the real OpenAI adapter), not a
reimplementation of it, so a drift between "what we test" and "what actually
runs" can't hide a false pass.
"""

import os

from openai import OpenAI
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.adapters.services.open_ai_adapter import OpenAILLMAdapter

from agent_builder import AgentBuilder


def openai_tools_for_node(builder: AgentBuilder, node_name: str) -> list[dict]:
    """The exact OpenAI tool-calling schema Pipecat would send for this node."""
    node_config = builder._make_node(builder._nodes_by_name[node_name])
    standard_tools = [f.to_function_schema() for f in node_config["functions"]]
    return OpenAILLMAdapter().to_provider_tools_format(ToolsSchema(standard_tools=standard_tools))


def ask_node(builder: AgentBuilder, node_name: str, user_message: str):
    """Send one user turn to a node's real persona+task+tools, return the tool calls made (if any)."""
    node = builder._nodes_by_name[node_name]
    persona = node.role_message or builder.config.persona
    task = "\n".join(m["content"] for m in node.task_messages)

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=builder.config.model,
        messages=[
            {"role": "system", "content": f"{persona}\n\n{task}"},
            {"role": "user", "content": user_message},
        ],
        tools=openai_tools_for_node(builder, node_name),
    )
    return response.choices[0].message.tool_calls or []
