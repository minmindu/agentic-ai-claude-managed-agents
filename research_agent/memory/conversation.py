"""
memory/conversation.py
-----------------------
Persistence for the `conversation` collection: one document per turn.
Collection name comes from config.settings.SETTINGS by default —
override via the collection_name param (mainly for tests) or the
COLLECTION_CONVERSATION env var (for real deployments).
"""

from datetime import datetime, timezone
from itertools import count
from pymongo.database import Database

from config.settings import SETTINGS


class ConversationRecorder:
    """
    Records turns for a single session, handling the seq counter locally.
    Create one instance per session, right when the session starts.
    """

    def __init__(
        self,
        db: Database,
        session_id: str,
        student_id: str,
        collection_name: str | None = None,
    ):
        self.db = db
        self.session_id = session_id
        self.student_id = student_id
        self.collection_name = collection_name or SETTINGS["collection_conversation"]
        self._seq = count(1)

    @property
    def _collection(self):
        return self.db[self.collection_name]

    def _base_doc(self, turn_type: str) -> dict:
        return {
            "session_id": self.session_id,
            "student_id": self.student_id,
            "seq": next(self._seq),
            "turn_type": turn_type,
            "timestamp": datetime.now(timezone.utc),
            "summarized": False,
            "summary_id": None,
        }

    def record_user_message(self, content: str) -> None:
        doc = self._base_doc("user_message")
        doc.update(role="user", content=content)
        self._collection.insert_one(doc)

    def record_assistant_message(self, content: str) -> None:
        """
        Call once, with the full accumulated text, after the stream loop
        exits — see agents/session.py: this runs after the
        `with client.beta.sessions.events.stream(...)` block, not inside
        the end_turn branch, so it still fires on stream exhaustion too.
        """
        doc = self._base_doc("assistant_message")
        doc.update(role="assistant", content=content)
        self._collection.insert_one(doc)

    def record_tool_call(self, tool_name: str, tool_input: dict, event_id: str) -> None:
        doc = self._base_doc("tool_call")
        doc.update(role="tool", tool_name=tool_name, content=tool_input, event_id=event_id)
        self._collection.insert_one(doc)

    def record_tool_result(
        self, tool_name: str, result, event_id: str, group_id: str, status: str
    ) -> None:
        doc = self._base_doc("tool_result")
        doc.update(
            role="tool", tool_name=tool_name, content=result,
            event_id=event_id, group_id=group_id, status=status,
        )
        self._collection.insert_one(doc)

    def tag_batch(self, event_ids: list[str], group_id: str) -> None:
        """
        Retro-fits group_id onto tool_call docs already written for this
        batch. Scoped by session_id so a shared event_id string can
        never leak a tag across sessions.
        """
        self._collection.update_many(
            {"session_id": self.session_id, "event_id": {"$in": event_ids}},
            {"$set": {"group_id": group_id}},
        )
