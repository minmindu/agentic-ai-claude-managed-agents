"""
memory/knowledge_base.py
-------------------------
The `knowledge_base` collection: durable, GLOBALLY-scoped findings the
agent has accumulated — not tied to one student or one session.

Contrast with conversation_summary:
  - conversation_summary answers "what did THIS student and I do together"
    (student-scoped, continuity).
  - knowledge_base answers "what does the agent KNOW, regardless of who
    asked" (global, reuse). student456 researches recurrent novae; the
    vetted finding lands here; when student789 asks something related next
    week the agent retrieves it instead of re-running arXiv/Tavily.

Write pattern is append (every finding is its own doc; duplicates are
fine, curation is a later pass). Nothing here expires — no TTL.

Schema (`knowledge_base` collection — one document per finding, global scope)
-----------------------------------------------------------------------------
    _id               : ObjectId
    content           : str                 # the fact/finding (embedded)
    topic             : str                 # short label (aligns with
                                            #   conversation_summary.topic)
    tags              : list[str]           # free-text tags for pre-filtering
    source            : str | None          # provenance: URL, session_id,
                                            #   or "manual"
    scope             : str                 # "global" (reserved for future
                                            #   "student"-scoped notes)
    created_at        : datetime (UTC)
    content_embedding : list[float] | None  # Voyage vector of content
    embedding_model   : str | None          # model that produced the vector

Note: no student_id — this store is cross-student by design.

Indexes (see memory/db.py): topic, tags, (created_at desc). The vector
index over content_embedding is a separate Atlas Search resource (name in
SETTINGS["vector_index_knowledge_base"]), not created by ensure_indexes().

--- memory: embeddings ---
`content` is embedded with Voyage at write time and stored as
`content_embedding`, identical pattern to conversation_summary. Of the
memory stores this is the one whose whole value is semantic recall, so
it's the strongest case for the vector.
"""

from datetime import datetime, timezone
from pymongo.database import Database

from config.settings import SETTINGS
from memory.embeddings import embed_text


class KnowledgeBaseStore:
    def __init__(self, db: Database, collection_name: str | None = None):
        self.db = db
        self.collection_name = collection_name or SETTINGS["collection_knowledge_base"]

    @property
    def _collection(self):
        return self.db[self.collection_name]

    def add_entry(
        self,
        content: str,
        topic: str,
        tags: list[str] | None = None,
        source: str | None = None,
        embed: bool = True,
    ) -> dict:
        """
        Append a new knowledge_base entry.

        Args:
            content: The fact or finding, plain text — this is what gets
                     embedded and later matched against queries.
            topic:   Short label (aligns with conversation_summary.topic).
            tags:    Optional free-text tags for cheap pre-filtering.
            source:  Provenance — a URL, a session_id, or "manual".
            embed:   When True (default), embed `content` and store
                     `content_embedding`. False for offline/test writes.
        """
        doc = {
            "content": content,
            "topic": topic,
            "tags": tags or [],
            "source": source,
            "scope": "global",  # reserved: room for "student"-scoped notes later
            "created_at": datetime.now(timezone.utc),
            "content_embedding": None,
            "embedding_model": None,
        }
        if embed:
            doc["content_embedding"] = embed_text(content, input_type="document")
            doc["embedding_model"] = SETTINGS["voyage_embedding_model"]

        result = self._collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    def search_knowledge_base(
        self, query: str, limit: int = 5, vector: bool = True, min_score: float = 0.0
    ) -> list[dict]:
        """
        Find existing entries relevant to a new research question, so the
        agent can reuse a prior finding instead of re-researching it.
        No student filter — this store is cross-student by design.

        Args:
            vector: True (default) → embed `query` (input_type="query") and
                    run Atlas $vectorSearch over `content_embedding`.
                    False → regex fallback (no Atlas index / Voyage key).
            min_score: Drop vector hits scoring below this threshold, so weak
                    matches never reach the caller. 0.0 (default) keeps every
                    hit. Only applies to the vector path — the regex fallback
                    has no score.
        """
        if not vector:
            return list(
                self._collection.find(
                    {
                        "$or": [
                            {"topic": {"$regex": query, "$options": "i"}},
                            {"content": {"$regex": query, "$options": "i"}},
                            {"tags": {"$regex": query, "$options": "i"}},
                        ]
                    }
                )
                .sort("created_at", -1)
                .limit(limit)
            )

        query_vector = embed_text(query, input_type="query")
        pipeline = [
            {
                "$vectorSearch": {
                    "index": SETTINGS["vector_index_knowledge_base"],
                    "path": "content_embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(limit * 20, 100),
                    "limit": limit,
                }
            },
            {
                "$project": {
                    "content": 1, "topic": 1, "tags": 1, "source": 1,
                    "created_at": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        results = list(self._collection.aggregate(pipeline))
        if min_score > 0:
            results = [d for d in results if d.get("score", 0.0) >= min_score]
        return results
