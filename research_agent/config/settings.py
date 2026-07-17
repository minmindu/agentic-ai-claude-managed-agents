"""
config/settings.py
------------------
Shared infrastructure config — things every agent in this repo needs.

Agent-specific config (name, model override, token limits, output paths)
lives in each agent's own file (e.g. agents/research_agent.py).

--- memory ---
MongoDB settings live here too, not in memory/db.py — this file is
already the single place env vars get read into config, and the memory
layer is shared infrastructure in the same sense api_key is. Read
SETTINGS["mongodb_..."] everywhere else in the memory layer rather than
calling os.environ.get() a second time.

--- memory: embeddings ---
The LLM that summarizes sessions is Claude (default_model). Embeddings
are a separate concern — Claude has no embedding endpoint — so the
memory layer's vector fields are produced by a Voyage AI model. These
are the same models Atlas Automated Embedding (autoEmbed) would call
for you; we call them by hand here so the embedding lives in the
document and the whole thing runs without an Atlas Search index yet.
"""

import os
from dotenv import load_dotenv

load_dotenv()

SETTINGS = {
    # Anthropic API key — shared by all agents
    "api_key": os.environ.get("ANTHROPIC_API_KEY"),

    # Default Claude model — agents can override this in their own AGENT_CONFIG
    "default_model": "claude-sonnet-4-6",

    # Shared cloud environment for all agent sessions
    "environment_name": "managed-agents-env",

    # --- memory ---
    # Atlas connection string. No default — memory.db.get_db() raises a
    # clear error if this is still None when it's actually needed,
    # rather than failing silently or guessing a connection string.
    "mongodb_uri": os.environ.get("DATABASE_URI"),

    # Database + collection names. All have defaults, since most setups
    # never need to change them — only override via .env if you're
    # running multiple environments against one cluster, or namespacing
    # collections for a multi-agent deployment.
    "mongodb_db": os.environ.get("DATABASE", "ai_memory"),
    "collection_conversation": os.environ.get("COLLECTION_CONVERSATION", "conversation"),
    "collection_conversation_summary": os.environ.get("COLLECTION_CONVERSATION_SUMMARY", "conversation_summary"),
    "collection_knowledge_base": os.environ.get("COLLECTION_KNOWLEDGE_BASE", "knowledge_base"),
    "collection_student": os.environ.get("COLLECTION_STUDENT", "student"),

    # --- memory: embeddings (Voyage AI) ---
    # Separate key from ANTHROPIC_API_KEY. Anthropic's own docs point at
    # Voyage for embeddings, so this is the "same ecosystem" choice.
    "voyage_api_key": os.environ.get("VOYAGE_API_KEY"),

    # Embedding model + its output dimensionality. These two MUST stay in
    # sync with each other AND with the numDimensions you set on the Atlas
    # Vector Search index. Changing the model later means re-embedding
    # every stored vector — that's why the model name is written onto each
    # document (see conversation_summary / knowledge_base), so a mismatch
    # is detectable rather than silent.
    #
    # NOTE: verify the dimension against the model you actually pick —
    # different Voyage models emit different sizes. 1024 is the default
    # for the voyage-3.x line; confirm before you build the index.
    "voyage_embedding_model": os.environ.get("VOYAGE_EMBEDDING_MODEL", "voyage-3.5"),
    "voyage_embedding_dims": int(os.environ.get("VOYAGE_EMBEDDING_DIMS", "1024")),

    # Names of the Atlas Vector Search indexes the memory layer queries.
    # These are Search-index resources (created via Atlas UI / Admin API),
    # not regular collection indexes — see memory/db.py.
    "vector_index_conversation_summary": os.environ.get(
        "VECTOR_INDEX_CONVERSATION_SUMMARY", "conversation_summary_vector_index"
    ),
    "vector_index_knowledge_base": os.environ.get(
        "VECTOR_INDEX_KNOWLEDGE_BASE", "knowledge_base_vector_index"
    ),

    # --- memory: retrieval threshold ---
    # Minimum vectorSearchScore for a retrieved summary/KB entry to be
    # considered "relevant" enough to inject. $vectorSearch ALWAYS returns
    # up to `limit` results even when the best match is unrelated, so
    # without a cutoff a brand-new question pulls in a stale past session
    # as if it were context. Filter below this score before injecting.
    #
    # CALIBRATE THIS against your own data — the right value depends on the
    # similarity metric in your Atlas index (cosine vs dotProduct vs
    # euclidean produce different score scales), so there is no universal
    # constant. Start here, eyeball real queries, adjust. Set to 0.0 to
    # disable filtering (inject whatever ranks top-k).
    "memory_min_similarity_score": float(
        os.environ.get("MEMORY_MIN_SIMILARITY_SCORE", "0.7")
    ),
}
