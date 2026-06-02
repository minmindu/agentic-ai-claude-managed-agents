"""
agents/research_agent.py
------------------------
Research-agent-specific configuration and factory function.

To add a new agent, follow the same pattern:
  1. Create agents/<your_agent>.py with its own SYSTEM_PROMPT, AGENT_CONFIG, and TOOL_MAPPING.
  2. Call setup.create_agent() with those values.
"""

import anthropic

from config.settings import SETTINGS
from agents.setup import create_agent
from tools.research_tools import (
    ARXIV_TOOL_DEF,     arxiv_search_tool,
    TAVILY_TOOL_DEF,    tavily_search_tool,
    WIKIPEDIA_TOOL_DEF, wikipedia_search_tool,
)

## Agent configuration and factory function
AGENT_CONFIG = {
    "name":                   "Research Agent",
    "model":                  SETTINGS["default_model"],
    "reflection_max_tokens":  10240, ## need more tokens if calling Claude Managed Agent with a long report to reflect on and rewrite.
    "html_max_tokens":        10240, ## need more tokens if calling Claude Managed Agent with a long report to reflect on and rewrite.
    "default_output_html":    "research_report.html",
}

## TODO: Note: word limit is not strictly necessary while using OPEN_AI APIs.
# 1 token ≈ 4 chars; 1 word ≈ 5 chars → 1 word ≈ 1.25 tokens.
# Derive the report word cap from the reflection budget so both stay in sync.
_report_max_words = int((AGENT_CONFIG["reflection_max_tokens"] - 1000) / 1.25)

SYSTEM_PROMPT = (
    "You are a research assistant that can search the web and arXiv to write detailed, "
    "accurate, and properly sourced research reports.\n\n"
    "Use tools when appropriate (e.g., to find scientific papers or web content).\n"
    "Cite sources whenever relevant. Do NOT omit citations for brevity.\n"
    "When possible, include full URLs (arXiv links, web sources, etc.).\n"
    "Use an academic tone, organize output into clearly labeled sections, and include "
    "inline citations or footnotes as needed.\n"
    "Do not include placeholder text such as '(citation needed)' or '(citations omitted)'.\n"
    f"Keep your final report concise: aim for {_report_max_words} words maximum."
)

TOOL_MAPPING: dict[str, callable] = {
    "arxiv_search_tool":     arxiv_search_tool,
    "tavily_search_tool":    tavily_search_tool,
    "wikipedia_search_tool": wikipedia_search_tool,
}


def create_research_agent(client: anthropic.Anthropic) -> str:
    """
    Create a Managed Agent configured for research tasks.

    Returns:
        The agent ID string.
    """
    return create_agent(
        client=client,
        name=AGENT_CONFIG["name"],
        model=AGENT_CONFIG["model"],
        system=SYSTEM_PROMPT,
        tools=[
            {"type": "agent_toolset_20260401"},
            ARXIV_TOOL_DEF,
            TAVILY_TOOL_DEF,
            WIKIPEDIA_TOOL_DEF,
        ],
    )
