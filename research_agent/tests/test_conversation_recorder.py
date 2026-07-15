"""
tests/test_conversation_recorder.py
-------------------------------------
Unit tests for memory.conversation.ConversationRecorder.
"""

import mongomock
import pytest

from memory.conversation import ConversationRecorder


@pytest.fixture
def db():
    client = mongomock.MongoClient()
    return client["research_agent_test"]


@pytest.fixture
def recorder(db):
    return ConversationRecorder(db=db, session_id="sess_test_001", student_id="student_ab12")


def test_seq_increments_across_turn_types(db, recorder):
    recorder.record_user_message("What is the ethics of AI in healthcare?")
    recorder.record_tool_call("tavily_search_tool", {"query": "AI ethics healthcare"}, event_id="evt_1")
    recorder.record_tool_result(
        "tavily_search_tool", [{"title": "...", "url": "https://x", "content": "..."}],
        event_id="evt_1", group_id="batch_1", status="success",
    )
    recorder.record_assistant_message("Here is the report...")

    turns = list(db.conversation.find({"session_id": "sess_test_001"}).sort("seq", 1))
    assert [turn["seq"] for turn in turns] == [1, 2, 3, 4]
    assert [turn["turn_type"] for turn in turns] == [
        "user_message", "tool_call", "tool_result", "assistant_message",
    ]


def test_new_documents_default_to_unsummarized(db, recorder):
    recorder.record_user_message("test")
    doc = db.conversation.find_one({"session_id": "sess_test_001"})
    assert doc["summarized"] is False
    assert doc["summary_id"] is None


def test_tool_call_and_result_share_event_id(db, recorder):
    recorder.record_tool_call("arxiv_search_tool", {"query": "transformers"}, event_id="evt_42")
    recorder.record_tool_result(
        "arxiv_search_tool", [{"title": "...", "url": "https://arxiv.org/abs/1", "content": None}],
        event_id="evt_42", group_id="batch_9", status="success",
    )
    call = db.conversation.find_one({"turn_type": "tool_call", "event_id": "evt_42"})
    result = db.conversation.find_one({"turn_type": "tool_result", "event_id": "evt_42"})
    assert call["event_id"] == result["event_id"] == "evt_42"


def test_tag_batch_retrofits_group_id_onto_existing_calls(db, recorder):
    recorder.record_tool_call("arxiv_search_tool", {"query": "AI ethics"}, event_id="evt_a")
    recorder.record_tool_call("tavily_search_tool", {"query": "AI ethics 2025"}, event_id="evt_b")
    recorder.record_tool_call("wikipedia_search_tool", {"query": "AI ethics"}, event_id="evt_c")

    untagged = list(db.conversation.find({"session_id": "sess_test_001", "turn_type": "tool_call"}))
    assert all("group_id" not in doc for doc in untagged)

    recorder.tag_batch(["evt_a", "evt_b", "evt_c"], group_id="sess_test_001-batch-evt_a")

    tagged = list(db.conversation.find({"session_id": "sess_test_001", "turn_type": "tool_call"}))
    assert len(tagged) == 3
    assert all(doc["group_id"] == "sess_test_001-batch-evt_a" for doc in tagged)


def test_tag_batch_does_not_leak_across_sessions(db):
    recorder_a = ConversationRecorder(db=db, session_id="sess_A", student_id="student_ab12")
    recorder_b = ConversationRecorder(db=db, session_id="sess_B", student_id="student_cd34")

    recorder_a.record_tool_call("arxiv_search_tool", {"query": "x"}, event_id="evt_shared")
    recorder_b.record_tool_call("tavily_search_tool", {"query": "y"}, event_id="evt_shared")
    recorder_a.tag_batch(["evt_shared"], group_id="group_for_A_only")

    doc_a = db.conversation.find_one({"session_id": "sess_A"})
    doc_b = db.conversation.find_one({"session_id": "sess_B"})
    assert doc_a["group_id"] == "group_for_A_only"
    assert "group_id" not in doc_b


def test_default_collection_name_comes_from_settings(db, recorder):
    """
    With no override, ConversationRecorder should write to whatever
    SETTINGS["collection_conversation"] resolves to (default: "conversation") —
    proving the config-driven default actually takes effect, not just that
    a hardcoded "conversation" string still happens to match it.
    """
    from config.settings import SETTINGS
    recorder.record_user_message("test")
    assert db[SETTINGS["collection_conversation"]].count_documents({}) == 1


def test_collection_name_override_actually_used(db):
    """
    Passing collection_name explicitly should write there instead of the
    configured default — this is the behavior .env's
    COLLECTION_CONVERSATION is meant to control in production.
    """
    custom_recorder = ConversationRecorder(
        db=db, session_id="sess_custom", student_id="student_ab12",
        collection_name="conversation_dev",
    )
    custom_recorder.record_user_message("test in a custom collection")

    assert db["conversation_dev"].count_documents({}) == 1
    assert db["conversation"].count_documents({}) == 0
