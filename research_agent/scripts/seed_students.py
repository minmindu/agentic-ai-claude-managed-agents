"""
scripts/seed_students.py
------------------------
Populate the `student` collection so personalization actually does
something. Until a student has a record, StudentStore.personalization_context()
returns None and build_memory_context() injects nothing about them — the
agent falls back to its default voice regardless of who's asking.

This is the WRITE side of the student store. In a real product these rows
would be created from a signup form / SIS import / an onboarding turn; here
we seed two contrasting profiles by hand so the difference is visible.

Run from the research_agent/ directory:
    python script/seed_students.py
"""

import sys
from pathlib import Path

# This script lives in research_agent/script/, so running it directly puts
# that subfolder on sys.path — not research_agent/ — and `import memory`
# fails. Put the project root (this file's parent's parent) on the path
# first so the memory/config packages resolve regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.db import get_db, ensure_indexes
from memory.student import StudentStore


# The two contrasting learners from the design discussion. Same agent,
# same question, deliberately different `register` so the injected system
# override — and therefore the agent's voice — changes per student.
SEED = [
    dict(
        student_id="student123",
        academic_level="postgraduate",
        register="academic",
        topics_of_interest=["radio astronomy", "recurrent novae"],
        notes="Wants primary-source papers and precise terminology; "
              "comfortable with dense technical prose.",
    ),
    dict(
        student_id="student456",
        academic_level="kid",
        register="simple",
        topics_of_interest=["space", "stars"],
        notes="Explain with plain words and everyday analogies; avoid jargon "
              "and define any term that can't be avoided.",
    ),
]


def seed(db) -> None:
    store = StudentStore(db)
    for row in SEED:
        doc = store.upsert(**row)
        # Show what the agent will actually see for this student.
        ctx = store.personalization_context(row["student_id"])
        print(f"\n✅ upserted {doc['student_id']}")
        print(f"   injected context -> {ctx}")


if __name__ == "__main__":
    db = get_db()
    ensure_indexes(db)
    seed(db)
    print("\nDone. build_memory_context() will now inject these profiles.")
