"""
memory/conversation_summary.py
--------------------
Builds one conversation_summary record from a completed session's raw
turns, then marks those turns as summarized. Called from main.py, on a
background thread, once Step 1's session_id is known.

Collection names come from config.settings.SETTINGS by default —
override via the *_collection params (mainly for tests).

Schema (`conversation_summary` collection — one document per summarized session)
--------------------------------------------------------------------------------
    _id               : ObjectId
    student_id        : str
    session_id        : str
    date              : str                 # ISO date, e.g. "2026-07-16"
    summary           : str                 # 2-3 sentence session summary
    topic             : str                 # short topic label
    open_thread       : str | None          # unresolved question to revisit
    sources_used      : list[str]           # URLs, derived deterministically
                                            #   from tool_result turns (not LLM)
    source_turns      : list[ObjectId]      # -> conversation._id docs folded in
    summary_embedding : list[float] | None  # Voyage vector of topic+summary
    embedding_model   : str | None          # model that produced the vector

Indexes (see memory/db.py): (student_id, date desc), sources_used, topic.
The vector index over summary_embedding is a separate Atlas Search resource
(name in SETTINGS["vector_index_conversation_summary"]), not created by
ensure_indexes().

--- memory: embeddings ---
The vector stored on each doc as `summary_embedding` is built from a
COMPOSED string: topic + summary (see _compose_embedding_input). The
topic anchors the crisp label; the summary carries the meaning. It's one
vector in one field — not a separate topic vector — which keeps the read
path a single $vectorSearch and maps cleanly onto an Atlas autoEmbed
"search on a view / $concat" setup later. `embedding_model` is written
alongside so a later model change is detectable rather than silent.

Read side has two halves, and BOTH are needed to "use" this store:
  1. find_relevant_past_summaries() — retrieve this student's relevant
     past sessions ($vectorSearch by default; regex fallback for tests).
  2. format_summaries_as_context() — turn those hits into a text block
     you inject at the start of the NEXT session so the agent has
     continuity. Retrieval alone does nothing until you feed it back in.
"""

import json
from datetime import datetime, timezone
from pymongo.database import Database
import anthropic

from config.settings import SETTINGS
from memory.embeddings import embed_text


def _compose_embedding_input(topic: str, summary: str) -> str:
    """
    The exact text that gets embedded for a summary doc. Single source of
    truth so the write path here and any future re-embed/back-fill script
    compose it identically — if these ever diverge, stored vectors and
    freshly-computed ones stop being comparable.
    """
    return f"{topic}\n\n{summary}"


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
    embed: bool = True,
) -> str | None:
    """
    Summarize a completed session and store it as a conversation_summary
    record. Safe to run on a background thread.

    Args:
        embed: When True (default), embed topic+summary with Voyage and
               store `summary_embedding`. Pass False in tests / offline
               runs where no VOYAGE_API_KEY is available.

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
        # --- memory: embeddings ---
        # Populated below when embed=True; kept as explicit keys (None
        # otherwise) so every doc has a uniform shape.
        "summary_embedding": None,
        "embedding_model": None,
    }

    # --- memory: embeddings ---
    # Embed topic + summary (composed), not the raw transcript: the summary
    # is the de-noised representation we want to match future queries
    # against, and the topic sharpens the label. input_type="document" —
    # this is the stored side.
    if embed:
        summary_doc["summary_embedding"] = embed_text(
            _compose_embedding_input(parsed["topic"], parsed["summary"]),
            input_type="document",
        )
        summary_doc["embedding_model"] = SETTINGS["voyage_embedding_model"]

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
    vector: bool = True,
    min_score: float | None = None,
) -> list[dict]:
    """
    Look up past sessions for THIS student relevant to a new question.
    Every read is student-scoped — continuity is per-person.

    The query is embedded with input_type="query" so it matches the
    input_type="document" vectors written by summarize_session(). Note the
    asymmetry is intentional: the stored side is composed topic+summary,
    the query side is just the incoming question — you enrich what you
    store, you don't rewrite what the user asked.

    Args:
        vector: When True (default), run Atlas $vectorSearch over
                `summary_embedding`. When False, regex match on
                topic/summary — no Atlas Search index or Voyage key
                required (used by the tests).
        min_score: Drop any hit whose vectorSearchScore is below this
                before returning, so an irrelevant top-k result never
                reaches the prompt. None -> use
                SETTINGS["memory_min_similarity_score"]; pass 0.0 to keep
                everything. Only applies on the vector path — regex
                results carry no score and are returned unfiltered.
    """
    if min_score is None:
        min_score = SETTINGS["memory_min_similarity_score"]
    summary_coll = db[summary_collection or SETTINGS["collection_conversation_summary"]]

    if not vector:
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

    # --- memory: embeddings (vector path) ---
    query_vector = embed_text(topic_query, input_type="query")
    pipeline = [
        {
            "$vectorSearch": {
                "index": SETTINGS["vector_index_conversation_summary"],
                "path": "summary_embedding",
                "queryVector": query_vector,
                "numCandidates": max(limit * 20, 100),
                "limit": limit,
                # student_id must be declared as a `filter` field on the
                # vector index for this pre-filter to work.
                "filter": {"student_id": student_id},
            }
        },
        {
            "$project": {
                "summary": 1, "topic": 1, "open_thread": 1,
                "sources_used": 1, "date": 1, "student_id": 1, "session_id": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    results = list(summary_coll.aggregate(pipeline))
    # Threshold: $vectorSearch returns top-k regardless of quality, so cut
    # anything below min_score before it can be injected.
    if min_score > 0:
        results = [d for d in results if d.get("score", 0.0) >= min_score]
    return results


def format_summaries_as_context(summaries: list[dict], max_chars: int = 1500) -> str | None:
    """
    Turn retrieved past summaries into a compact text block to inject at
    the START of a new session (see agents/session.py's context_preamble).
    This is the half that actually "uses" the store — retrieval without
    injection changes nothing about what the agent produces.

    Returns None when there's nothing relevant, so the caller can skip the
    preamble entirely rather than injecting an empty header.

    Design choices:
      - Leads with an instruction to use the context only if relevant and
        not to fabricate continuity — retrieved != relevant, and a weak
        vector hit shouldn't railroad a genuinely new question.
      - Includes open_thread explicitly: a returning student is often
        chasing the question left open last time, not the settled finding.
      - Caps total length so a chatty history can't crowd out the actual
        research prompt.
    """
    if not summaries:
        return None

    lines = [
        "Context from this student's earlier research sessions "
        "(use only if relevant to the current question; do not fabricate "
        "continuity that isn't there):",
    ]
    for s in summaries:
        date = s.get("date", "unknown date")
        topic = s.get("topic", "untitled")
        entry = f"- [{date}] {topic}: {s.get('summary', '').strip()}"
        if s.get("open_thread"):
            entry += f" (left open: {s['open_thread'].strip()})"
        srcs = s.get("sources_used") or []
        if srcs:
            entry += f" Sources: {', '.join(srcs[:3])}"
        lines.append(entry)

    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[:max_chars].rsplit("\n", 1)[0] + "\n- ...(older sessions trimmed)"
    return block
