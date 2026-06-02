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
"""

import anthropic
import json


def run_session(
    client: anthropic.Anthropic,
    agent_id: str,
    environment_id: str,
    user_message: str,
    tool_mapping: dict[str, callable],
    title: str = "Research session",
) -> str:
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
        title:          Human-readable label for the session.

    Returns:
        The full agent response text.
    """
    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title=title,
    )
    print(f"   Session started: {session.id}")

    text_buffer: list[str] = []
    events_by_id: dict[str, object] = {}

    with client.beta.sessions.events.stream(session.id) as stream:
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
                    print(f"\n🛠️  {event.name}({event.input})")

                case "session.status_idle":
                    stop = event.stop_reason
                    if stop and stop.type == "requires_action":
                        for event_id in stop.event_ids:
                            tool_event = events_by_id[event_id]
                            print(f"\n   ↳ executing {tool_event.name}...")
                            try:
                                result = tool_mapping[tool_event.name](**tool_event.input)
                            except Exception as exc:
                                result = {"error": str(exc)}
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

    return "".join(text_buffer)
