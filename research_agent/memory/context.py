"""
memory/context.py
------------------
The memory READ / assembly entry point.

This is where the memory layer's read side is composed into the single
text block that primes a session. It pulls two things together:
  - the student profile (StudentStore) — how to talk to this person, and
  - relevant past-session summaries (conversation_summary) — what we've
    already covered together, filtered by a similarity-score threshold.

Kept separate from workflows/report.py on purpose: report.py just runs
the agent and doesn't need to know WHERE its context came from. The
orchestrator (main.run_workflow) calls build_memory_context() and hands
the result to the report step as context_preamble.
"""

from memory.student import StudentStore
from memory.conversation_summary import (
    find_relevant_past_summaries,
    format_summaries_as_context,
)


def build_memory_context(
    db,
    student_id: str,
    topic: str,
    use_vector: bool = True,
    min_score: float | None = None,
) -> str | None:
    """
    Assemble the preamble injected at session start. Returns None if there's
    neither a student profile nor any relevant past session — in which case
    the caller sends the bare question with the agent's own system prompt.

    Args:
        min_score: Similarity-score cutoff for past summaries. None ->
            SETTINGS["memory_min_similarity_score"]. This is the knob to
            tune: raise it to admit only very-close past sessions, lower
            it to be more permissive. Only affects the vector path.
    """
    parts: list[str] = []

    # Who is this student — drives tone/depth. (student store: exact-key read)
    profile = StudentStore(db).personalization_context(student_id)
    if profile:
        parts.append(profile)

        

    # What have we covered before — drives continuity. Score-thresholded so
    # a weak match is dropped BEFORE injection rather than cautioned against
    # in the prompt. (conversation_summary: student-scoped semantic retrieval)
    past = find_relevant_past_summaries(
        db, student_id, topic, vector=use_vector, min_score=min_score
    )
    summary_block = format_summaries_as_context(past)
    if summary_block:
        parts.append(summary_block)

    return "\n\n".join(parts) if parts else None
