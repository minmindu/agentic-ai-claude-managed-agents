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
    "mongodb_db": os.environ.get("DATABASE", "research_agent"),
    "collection_conversation": os.environ.get("COLLECTION_CONVERSATION", "conversation"),
    "collection_conversation_summary": os.environ.get("COLLECTION_CONVERSATION_SUMMARY", "conversation_summary"),
}
