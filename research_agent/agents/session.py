"""
agents/session.py
-----------------
Manages a Managed Agent session: starting it, streaming events, and
dispatching custom tool calls back to the executor.

--- memory ---
This version persists every turn to MongoDB via
memory.conversation.ConversationRecorder. Conversation summarization is
triggered at the workflow level, not here.

--- memory: read path (session system override) ---
Memory context (student profile + relevant past summaries) is injected
via a per-SESSION system-prompt OVERRIDE, not by prepending to the user
message. The Managed Agents API lets you override `system` for a single
session without creating a new agent version. This is the placement the
memory vendors (e.g. Mem0) use too: retrieved context belongs in the
system prompt; the user turn should carry only the student's actual
question.

Two consequences the code accounts for:
  1. An override REPLACES the agent's system prompt — it doesn't append.
     So the caller must pass base_system_prompt, and we send
     base + context. Without a base prompt we simply don't override
     (the agent's baked-in system stays in effect).
  2. The recorded user turn stays the student's real words either way,
     so the raw `conversation` log is never polluted with injected
     memory.
"""

import anthropic
import json

from memory.conversation import ConversationRecorder  # --- memory ---
from pymongo.database import Database  # --- memory ---


def run_session(
    client: anthropic.Anthropic,
    agent_id: str,
    environment_id: str,
    user_message: str,
    tool_mapping: dict[str, callable],
    db: Database,  # --- memory ---
    student_id: str,  # --- memory ---
    title: str = "Research session",
    base_system_prompt: str | None = None,   # --- memory: read path ---
    context_preamble: str | None = None,     # --- memory: read path ---
) -> tuple[str, str]:
    """
    Start a session, send a user message, stream all events, and return the
    final assistant text once the session goes idle with stop_reason=end_turn.

    Args:
        base_system_prompt: The agent's base system prompt. Required to use
            a session system override, because the override REPLACES rather
            than appends. If None, no override is applied and the agent's
            own system prompt is used unchanged.
        context_preamble: Memory context to inject. When provided together
            with base_system_prompt, the session runs with
            `base_system_prompt + context_preamble` as its system prompt.
            The RECORDED user turn never includes it.

    Returns:
        (report_text, session_id).
    """
    # --- memory: read path --- build the per-session system override.
    session_kwargs = {
        "agent": agent_id,
        "environment_id": environment_id,
        "title": title,
    }
    if context_preamble and base_system_prompt:
        override_system = f"{base_system_prompt}\n\n{context_preamble}"
        # Pass `agent` as an override object carrying the per-session `system`
        # alongside the id. The `system` (and model / tools / mcp_servers /
        # skills) override is ONLY valid under type "agent_with_overrides" —
        # the plain "agent" type accepts just id/type/version, so putting
        # `system` there is rejected as an unknown field. See the SDK's
        # BetaManagedAgentsAgentWithOverridesParams.
        session_kwargs["agent"] = {
            "type": "agent_with_overrides",
            "id": agent_id,
            "system": override_system,
        }
    elif context_preamble and not base_system_prompt:
        # Guard: we have context but no base prompt to compose with.
        # Overriding would wipe the agent's system prompt, so we skip the
        # override rather than silently degrade the agent's behavior.
        print("   [memory] context_preamble supplied without base_system_prompt; "
              "skipping system override (agent's own system prompt kept).")

    session = client.beta.sessions.create(**session_kwargs)
    print(f"   Session started: {session.id}")

    recorder = ConversationRecorder(db=db, session_id=session.id, student_id=student_id)  # --- memory ---

    text_buffer: list[str] = []
    events_by_id: dict[str, object] = {}

    with client.beta.sessions.events.stream(session.id) as stream:
        # --- memory --- record + send the student's real words. Memory
        # context now lives in the system override, so the user turn is
        # clean on both the wire and the log.
        recorder.record_user_message(user_message)

        client.beta.sessions.events.send(
            session.id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": user_message}],
                }
            ],
        )

        for event in stream:
            match event.type:

                case "agent.message":
                    for block in event.content:
                        if block.type == "text":
                            text_buffer.append(block.text)
                            print(block.text, end="", flush=True)

                case "agent.tool_use":
                    print(f"\n[Built-in tool: {event.name}]")

                case "agent.custom_tool_use":
                    events_by_id[event.id] = event
                    recorder.record_tool_call(  # --- memory ---
                        tool_name=event.name, tool_input=event.input, event_id=event.id
                    )
                    print(f"\n{event.name}({event.input})")

                case "session.status_idle":
                    stop = event.stop_reason
                    if stop and stop.type == "requires_action":
                        group_id = f"{session.id}-batch-{stop.event_ids[0]}"  # --- memory ---
                        recorder.tag_batch(list(stop.event_ids), group_id)  # --- memory ---

                        for event_id in stop.event_ids:
                            tool_event = events_by_id[event_id]
                            print(f"\n   executing {tool_event.name}...")
                            try:
                                result = tool_mapping[tool_event.name](**tool_event.input)
                                status = "error" if (  # --- memory ---
                                    isinstance(result, list) and result and "error" in result[0]
                                ) else "success"
                            except Exception as exc:
                                result = {"error": str(exc)}
                                status = "error"  # --- memory ---

                            recorder.record_tool_result(  # --- memory ---
                                tool_name=tool_event.name, result=result,
                                event_id=event_id, group_id=group_id, status=status,
                            )

                            client.beta.sessions.events.send(
                                session.id,
                                events=[
                                    {
                                        "type": "user.custom_tool_result",
                                        "custom_tool_use_id": event_id,
                                        "content": [
                                            {"type": "text", "text": json.dumps(result)},
                                        ],
                                    },
                                ],
                            )

                    elif stop and stop.type == "end_turn":
                        print("\nFinal answer received.")
                        break

                case "session.status_terminated":
                    raise RuntimeError(f"Session terminated unexpectedly: {event}")

                case _:
                    print(f"   [DEBUG event]: type={event.type!r} | {event}")

    recorder.record_assistant_message("".join(text_buffer))  # --- memory ---

    return "".join(text_buffer), session.id
