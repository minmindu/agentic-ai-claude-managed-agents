"""
workflows/report.py
------------------
Step 1: Generate a research report using the Claude Managed Agent.

This file's only job is the agent call. 
Memory context (student profile + relevant past-session summaries) is assembled elsewhere — see
memory/context.build_memory_context() — and handed in as context_preamble
by the orchestrator (main.run_workflow). run_session composes it with the
agent's base SYSTEM_PROMPT and applies it as a per-session system override.
"""

import anthropic

from agents.session import run_session
from agents.research_agent import SYSTEM_PROMPT  # base system prompt to compose with


def generate_research_report_with_tools(
    client: anthropic.Anthropic,
    prompt: str,
    agent_id: str,
    environment_id: str,
    tool_mapping: dict[str, callable],
    db,  # --- memory ---
    student_id: str,  # --- memory ---
    context_preamble: str | None = None,  # --- memory: read path ---
) -> tuple[str, str]:
    """
    Run a Managed Agent session to produce a sourced research report.

    The agent loop — tool-call decisions and retries — is handled by the
    Managed Agents harness. This function only starts the session, sends the
    message, and returns once it goes idle with stop_reason == "end_turn".

    Args:
        client:           Authenticated Anthropic client.
        prompt:           The research topic / user query.
        agent_id:         Pre-created agent ID.
        environment_id:   Pre-created environment ID.
        tool_mapping:     Name → callable map for this agent's custom tools.
        db:               database layer for memory (in this case, it is a MongoDB ), passed to run_session so every turn
                          is recorded (ConversationRecorder) — needed even when there's no memory context to inject.
        student_id:       Student the session belongs to; used for turn recording and memory scoping.
        context_preamble: Pre-assembled memory context (see
                          memory/context.build_memory_context). Applied as a per-session system override on top of SYSTEM_PROMPT;
                          None → the agent keeps its own system prompt.

    Returns:
        (report_text, session_id).
    """
    print(f"\n--- Step 1: Generating research report ---")
    print(f"   Topic: {prompt}\n")

    if context_preamble:
        print(f"   Injecting memory context via system override "
              f"({len(context_preamble)} chars)")

    report, session_id = run_session(
        client=client,
        agent_id=agent_id,
        environment_id=environment_id,
        user_message=prompt,
        tool_mapping=tool_mapping,
        db=db,  # --- memory ---
        student_id=student_id,  # --- memory ---
        title=f"Research: {prompt[:60]}",
        base_system_prompt=SYSTEM_PROMPT,   # --- memory: read path ---
        context_preamble=context_preamble,  # --- memory: read path ---
    )
    print(f"\n   Final report length: {len(report)} chars")
    return report, session_id
