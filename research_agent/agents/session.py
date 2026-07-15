"""
agents/session.py
-----------------
Manages a Managed Agent session: starting it, streaming events, and
dispatching custom tool calls back to the executor.

This is the core replacement for the manual `for _ in range(max_turns):`
agent loop in the original script. The harness handles:
  - Deciding which tool to call (and when to stop)
  - Retries and error recovery inside the container
  - Conversation history and context management
  - Prompt caching

Your code only needs to handle `agent.custom_tool_use` events and stop on `end_turn`.
The tool_mapping is supplied by the caller so this module stays agent-agnostic.

--- memory ---
This version additionally persists every turn to MongoDB via memory.conversation.ConversationRecorder,
Conversation summarization will be trigger in its workflow level, not in the session leve.
Everything marked with a "# --- memory ---" comment is new; everything
else is unchanged from the original.
"""

import anthropic
import json

# --- memory ---
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
)  -> tuple[str, str]:  # --- memory --- (now also returns session_id)
    """
    Start a session, send a user message, stream all events, and return the
    final assistant text once the session goes idle with stop_reason=end_turn.

    Custom tool call flow (per the Managed Agents docs):
      1. Claude emits `agent.custom_tool_use` → session pauses.
      2. Session emits `session.status_idle` with stop_reason.type == "requires_action".
      3. We execute the tool and send back `user.custom_tool_result` for each blocked event.
      4. Session resumes automatically once all blocking events are resolved.

    Args:
        client:         Authenticated Anthropic client.
        agent_id:       ID of the pre-created agent.
        environment_id: ID of the pre-created environment.
        user_message:   The research prompt to send.
        tool_mapping:   Name → callable map for this agent's custom tools.
        db:             MongoDB database handle (memory layer).       # --- memory ---
        student_id:     The student this session belongs to.          # --- memory ---
        title:          Human-readable label for the session.

    Returns:
        A (report_text, session_id) tuple. report_text is the full agent
        response text; session_id lets the caller pass through Step 2/3
        output association if needed later.                          # --- memory ---
    """

    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title=title,
    )
    print(f"   Session started: {session.id}")

    recorder = ConversationRecorder(db=db, session_id=session.id, student_id=student_id)  # --- memory ---

    text_buffer: list[str] = []
    events_by_id: dict[str, object] = {}

    with client.beta.sessions.events.stream(session.id) as stream:
        # --- memory ---
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
                    print(f"\n🛠️  [Built-in tool: {event.name}]")

                case "agent.custom_tool_use":
                    events_by_id[event.id] = event
                    # --- memory ---
                    recorder.record_tool_call(
                        tool_name=event.name, tool_input=event.input, event_id=event.id
                    )

                    print(f"\n🛠️  {event.name}({event.input})")

                case "session.status_idle":
                    stop = event.stop_reason
                    if stop and stop.type == "requires_action":
                        # --- memory ---
                        group_id = f"{session.id}-batch-{stop.event_ids[0]}"
                        recorder.tag_batch(list(stop.event_ids), group_id)

                        for event_id in stop.event_ids:
                            tool_event = events_by_id[event_id]
                            print(f"\n   ↳ executing {tool_event.name}...")
                            try:
                                result = tool_mapping[tool_event.name](**tool_event.input)
                                # --- memory ---
                                status = "error" if (
                                    isinstance(result, list) and result and "error" in result[0]
                                ) else "success"
                            except Exception as exc:
                                result = {"error": str(exc)}
                                status = "error"  # --- memory ---

                            # --- memory ---
                            recorder.record_tool_result(
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
                        print("\n✅ Final answer received.")
                        break

                case "session.status_terminated":
                    raise RuntimeError(f"Session terminated unexpectedly: {event}")

                case _:
                    print(f"   [DEBUG event]: type={event.type!r} | {event}")

    recorder.record_assistant_message("".join(text_buffer))

    result = "".join(text_buffer), session.id
    return result
