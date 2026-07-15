"""
memory/conversation_summary.py
--------------------
Builds one conversation_summary record from a completed session's raw
turns, then marks those turns as summarized. Called from main.py, on a
background thread, once Step 1's session_id is known.

Collection names come from config.settings.SETTINGS by default —
override via the *_collection params (mainly for tests).
"""

import json
from datetime import datetime, timezone
from pymongo.database import Database
import anthropic

from config.settings import SETTINGS


def _extract_sources_used(turns: list[dict]) -> list[str]:
    """
    Built deterministically from tool_result documents — never derived
    from the LLM.
    """
    sources = []
    for turn in turns:
        if turn["turn_type"] != "tool_result" or turn.get("status") != "success":
            continue
        items = turn["content"] if isinstance(turn["content"], list) else [turn["content"]]
        for item in items:
            url = item.get("url") if isinstance(item, dict) else None
            if url and url not in sources:
                sources.append(url)
    return sources


def _build_transcript(turns: list[dict]) -> str:
    lines = []
    for turn in turns:
        if turn["turn_type"] in ("user_message", "assistant_message"):
            lines.append(f"{turn['role']}: {turn['content']}")
        elif turn["turn_type"] == "tool_call":
            lines.append(f"[called {turn['tool_name']} with {turn['content']}]")
        elif turn["turn_type"] == "tool_result":
            n = len(turn["content"]) if isinstance(turn["content"], list) else 1
            lines.append(f"[{turn['tool_name']} returned {n} result(s)]")
    return "\n".join(lines)


def summarize_session(
    client: anthropic.Anthropic,
    db: Database,
    session_id: str,
    student_id: str,
    conversation_collection: str | None = None,
    summary_collection: str | None = None,
) -> str | None:
    """
    Summarize a completed session and store it as a conversation_summary
    record. Safe to run on a background thread.

    Returns:
        The inserted conversation_summary document's _id, or None if the
        session had no turns to summarize.
    """
    conv_coll = db[conversation_collection or SETTINGS["collection_conversation"]]
    summary_coll = db[summary_collection or SETTINGS["collection_conversation_summary"]]

    turns = list(conv_coll.find({"session_id": session_id}).sort("seq", 1))
    if not turns:
        return None

    sources_used = _extract_sources_used(turns)
    transcript = _build_transcript(turns)

    # Force structured output via tool use: Claude returns the fields as a
    # validated tool_use.input dict, so there's no free-form text to parse
    # (the model otherwise tends to wrap JSON in ```json fences or add a
    # preamble, which broke json.loads).
    summary_tool = {
        "name": "record_summary",
        "description": "Record the structured summary of a research session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "2-3 sentence summary separating settled "
                    "findings from open questions.",
                },
                "topic": {
                    "type": "string",
                    "description": "Short topic label for the session.",
                },
                "open_thread": {
                    "type": ["string", "null"],
                    "description": "An unresolved question to revisit, or null "
                    "if there is none.",
                },
            },
            "required": ["summary", "topic", "open_thread"],
        },
    }

    response = client.messages.create(
        model=SETTINGS["default_model"],
        max_tokens=500,
        tools=[summary_tool],
        tool_choice={"type": "tool", "name": "record_summary"},
        messages=[{
            "role": "user",
            "content": (
                "Summarize this research session. Separate settled findings "
                "from open questions. Do not invent facts or connections not "
                "present in the transcript below.\n\n" + transcript
            ),
        }],
    )

    parsed = next(
        (block.input for block in response.content if block.type == "tool_use"),
        None,
    )
    if parsed is None:
        raise RuntimeError(
            f"No tool_use block in summary response for session {session_id}"
        )

    summary_doc = {
        "student_id": student_id,
        "session_id": session_id,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "summary": parsed["summary"],
        "topic": parsed["topic"],
        "sources_used": sources_used,
        "open_thread": parsed.get("open_thread"),
        "source_turns": [turn["_id"] for turn in turns],
    }
    result = summary_coll.insert_one(summary_doc)

    conv_coll.update_many(
        {"session_id": session_id},
        {"$set": {"summarized": True, "summary_id": result.inserted_id}},
    )
    return result.inserted_id


def find_relevant_past_summaries(
    db: Database,
    student_id: str,
    topic_query: str,
    limit: int = 5,
    summary_collection: str | None = None,
) -> list[dict]:
    """
    Look up past sessions for this student relevant to a new question.

    PRODUCTION NOTE: should run Atlas hybrid search ($vectorSearch over
    the auto-embedded `summary` field + $search on topic/sources_used).
    Falls back to a plain regex match here so it's testable without a
    live Atlas cluster.
    """
    summary_coll = db[summary_collection or SETTINGS["collection_conversation_summary"]]
    return list(
        summary_coll.find(
            {
                "student_id": student_id,
                "$or": [
                    {"topic": {"$regex": topic_query, "$options": "i"}},
                    {"summary": {"$regex": topic_query, "$options": "i"}},
                ],
            }
        )
        .sort("date", -1)
        .limit(limit)
    )
