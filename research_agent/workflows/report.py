"""
workflows/report.py
------------------
Step 1: Generate a research report using the Claude Managed Agent.

The agent decides autonomously which tools to call (arXiv, Tavily, Wikipedia,
or the built-in web_search / web_fetch) and when to stop. Your code just
runs the session and receives the final text.
"""

import anthropic

from agents.session import run_session


def generate_research_report_with_tools(
    client: anthropic.Anthropic,
    prompt: str,
    agent_id: str,
    environment_id: str,
    tool_mapping: dict[str, callable],
) -> str:
    """
    Run a Managed Agent session to produce a sourced research report.

    The agent loop — including tool-call decisions and retries — is handled
    by the Managed Agents harness. Your code only needs to:
      1. Start a session
      2. Send the user message
      3. Execute custom tool calls when Claude asks for them
      4. Stop when the session goes idle with stop_reason == "end_turn"

    Args:
        client:         Authenticated Anthropic client.
        prompt:         The research topic / user query.
        agent_id:       Pre-created agent ID.
        environment_id: Pre-created environment ID.
        tool_mapping:   Name → callable map for this agent's custom tools.

    Returns:
        Full report text from the agent.
    """
    print(f"\n--- Step 1: Generating research report ---")
    print(f"   Topic: {prompt}\n")

    print(f"   Environment started within ID: {environment_id}")

    result = run_session(
        client=client,
        agent_id=agent_id,
        environment_id=environment_id,
        user_message=prompt,
        tool_mapping=tool_mapping,
        title=f"Research: {prompt[:60]}",
    )
    print(f"\n   Final report length: {len(result)} chars")
    print(f"DEBUG: report length = {len(result)}, preview = {result[:200]!r}")
    
    return result
