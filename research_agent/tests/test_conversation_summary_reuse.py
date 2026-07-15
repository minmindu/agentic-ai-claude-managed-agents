"""
tests/test_conversation_summary_reuse.py
------------------------------------------
Shows how conversation_summary gets used by a later run when the same
student asks a similar question again.
"""

from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from memory.conversation_summary import find_relevant_past_summaries


STUDENT_A = "student_ab12"
STUDENT_B = "student_cd34"


@pytest.fixture
def db():
    client = mongomock.MongoClient()
    return client["research_agent_test"]


def _seed_session_one(db):
    db.conversation_summary.insert_one({
        "student_id": STUDENT_A, "session_id": "sess_001",
        "date": (datetime.now(timezone.utc) - timedelta(days=21)).date().isoformat(),
        "summary": (
            "Researched the ethics of AI in healthcare, covering bias in "
            "diagnostic models and informed-consent challenges. Found three "
            "sources on algorithmic bias in clinical decision support."
        ),
        "topic": "ethics of AI in healthcare",
        "sources_used": ["https://arxiv.org/abs/2310.08659", "https://arxiv.org/abs/2401.11223"],
        "open_thread": "wants a deeper comparison of regulatory approaches (EU vs US) next time",
        "source_turns": [],
    })
    db.conversation_summary.insert_one({
        "student_id": STUDENT_A, "session_id": "sess_002",
        "date": (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat(),
        "summary": "Researched transformer efficiency techniques, focused on quantization.",
        "topic": "transformer efficiency",
        "sources_used": ["https://arxiv.org/abs/2402.00001"],
        "open_thread": None, "source_turns": [],
    })
    db.conversation_summary.insert_one({
        "student_id": STUDENT_B, "session_id": "sess_003",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "summary": "Researched AI ethics in healthcare from a policy perspective.",
        "topic": "ethics of AI in healthcare",
        "sources_used": ["https://arxiv.org/abs/2311.00002"],
        "open_thread": None, "source_turns": [],
    })


def test_second_session_finds_the_first(db):
    _seed_session_one(db)
    matches = find_relevant_past_summaries(db, student_id=STUDENT_A, topic_query="ethics of AI")
    assert len(matches) == 1
    assert matches[0]["session_id"] == "sess_001"


def test_unrelated_topic_does_not_match(db):
    _seed_session_one(db)
    matches = find_relevant_past_summaries(db, student_id=STUDENT_A, topic_query="quantum computing")
    assert matches == []


def test_other_students_sessions_never_leak(db):
    _seed_session_one(db)
    matches = find_relevant_past_summaries(db, student_id=STUDENT_A, topic_query="ethics of AI")
    assert "sess_003" not in [m["session_id"] for m in matches]


def test_orientation_message_built_from_match(db):
    _seed_session_one(db)
    matches = find_relevant_past_summaries(db, student_id=STUDENT_A, topic_query="ethics of AI")
    prior = matches[0]
    orientation = (
        f"Note: this student researched a similar topic on {prior['date']}. "
        f"Prior sources used: {', '.join(prior['sources_used'])}. "
        f"Open thread from that session: {prior['open_thread']}."
    )
    assert "2310.08659" in orientation
    assert "regulatory approaches" in orientation


def test_summary_collection_override_actually_used(db):
    """
    Same override guarantee as ConversationRecorder — proves
    find_relevant_past_summaries respects an explicit collection name
    rather than always reading the configured default.
    """
    db["summaries_dev"].insert_one({
        "student_id": STUDENT_A, "session_id": "sess_dev",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "summary": "Researched ethics of AI in a dev collection.",
        "topic": "ethics of AI in healthcare",
        "sources_used": [], "open_thread": None, "source_turns": [],
    })

    default_matches = find_relevant_past_summaries(db, student_id=STUDENT_A, topic_query="ethics of AI")
    dev_matches = find_relevant_past_summaries(
        db, student_id=STUDENT_A, topic_query="ethics of AI", summary_collection="summaries_dev"
    )

    assert default_matches == []
    assert len(dev_matches) == 1
    assert dev_matches[0]["session_id"] == "sess_dev"
