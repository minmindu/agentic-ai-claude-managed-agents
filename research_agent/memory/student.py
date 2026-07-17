"""
memory/student.py
------------------
The `student` collection: one document per student — the "who is this
person" record used to personalize a session BEFORE the agent writes a
word.

This store is different in kind from the other three. conversation /
conversation_summary / knowledge_base are logs and knowledge
(append-heavy, time-ordered, some of them vector-searched). `student` is
STATE: exactly one canonical doc per student_id, upserted in place, read
by exact key. No embedding, no vector, no TTL — you look a student up by
their id, you don't search for them by meaning.

Kept deliberately small and hand-editable: it's context to inject into
the system prompt, not a place to log events.
"""

from datetime import datetime, timezone
from pymongo.database import Database
from pymongo import ReturnDocument

from config.settings import SETTINGS


class StudentStore:
    def __init__(self, db: Database, collection_name: str | None = None):
        self.db = db
        self.collection_name = collection_name or SETTINGS["collection_student"]

    @property
    def _collection(self):
        return self.db[self.collection_name]

    def get(self, student_id: str) -> dict | None:
        return self._collection.find_one({"student_id": student_id})

    def upsert(
        self,
        student_id: str,
        academic_level: str | None = None,
        register: str | None = None,
        topics_of_interest: list[str] | None = None,
        notes: str | None = None,
    ) -> dict:
        """
        Create or update a student record. Only fields explicitly passed
        (non-None) are set, so updating one field never clobbers the rest.

        academic_level and register are kept separate on purpose: level is
        "how advanced" (postgraduate / undergraduate / kid) and register is
        "how to talk" (academic / simple). They usually correlate — a
        postgrad wants academic prose, a kid wants plain language — but not
        always, and the thing the agent needs at prompt time is register.
        """
        now = datetime.now(timezone.utc)
        set_fields = {"updated_at": now}
        for key, value in (
            ("academic_level", academic_level),
            ("register", register),
            ("topics_of_interest", topics_of_interest),
            ("notes", notes),
        ):
            if value is not None:
                set_fields[key] = value

        return self._collection.find_one_and_update(
            {"student_id": student_id},
            {
                "$set": set_fields,
                "$setOnInsert": {"student_id": student_id, "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    def personalization_context(self, student_id: str) -> str | None:
        """
        A short natural-language snippet describing this student, to append
        to the agent's system prompt at session start. Returns None when
        there's no record yet — callers fall back to the default prompt.
        """
        student = self.get(student_id)
        if student is None:
            return None

        parts = []
        if student.get("academic_level"):
            parts.append(f"a {student['academic_level']} student")
        if student.get("register"):
            parts.append(f"prefers a {student['register']} explanation style")
        if student.get("topics_of_interest"):
            parts.append("has previously shown interest in: " + ", ".join(student["topics_of_interest"]))
        if student.get("notes"):
            parts.append(student["notes"])

        if not parts:
            return None
        return "This student is " + "; ".join(parts) + "."
