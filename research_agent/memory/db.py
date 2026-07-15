"""
memory/db.py
------------
Shared MongoDB connection for the memory layer.

Create ONE MongoClient per process — pass the returned handle down
through run_workflow() / run_session() rather than calling get_db()
again anywhere else.

Connection details (URI, database name, collection names) all come
from config.settings.SETTINGS — see that file for the .env variables
that control them. This module doesn't read os.environ directly, so
there's exactly one place configuration is resolved.
"""

from pymongo import MongoClient
from pymongo.database import Database

from config.settings import SETTINGS


def get_db(uri: str | None = None, db_name: str | None = None) -> Database:
    """
    Return a MongoDB database handle for the memory layer.

    Args:
        uri:     Atlas connection string. Defaults to SETTINGS["mongodb_uri"].
        db_name: Database name. Defaults to SETTINGS["mongodb_db"].

    Returns:
        A pymongo Database instance.
    """
    uri = uri or SETTINGS["mongodb_uri"]
    if not uri:
        raise RuntimeError("DATABASE_URI is not set. Add it to your .env file.")
    db_name = db_name or SETTINGS["mongodb_db"]
    client = MongoClient(uri)
    return client[db_name]


def ensure_indexes(db: Database) -> None:
    """
    Create the plain (non-Search) indexes the memory layer depends on.
    Safe to call repeatedly — create_index is a no-op if an equivalent
    index already exists.

    NOTE: the Atlas Vector/Search index that auto-embeds
    conversation_summary.summary (Atlas Automated Embedding / autoEmbed)
    is NOT created here — that's a Search-index resource configured via
    the Atlas UI or Admin API, not a regular collection index.
    """
    conversation = db[SETTINGS["collection_conversation"]]
    conversation.create_index([("session_id", 1), ("seq", 1)])
    conversation.create_index([("student_id", 1)])
    conversation.create_index("event_id")
    # 90-day retention on conversation — conversation decays, conversation_summary does not.
    conversation.create_index("timestamp", expireAfterSeconds=90 * 24 * 60 * 60)

    summary = db[SETTINGS["collection_conversation_summary"]]
    summary.create_index([("student_id", 1), ("date", -1)])
    summary.create_index("sources_used")
    summary.create_index("topic")
