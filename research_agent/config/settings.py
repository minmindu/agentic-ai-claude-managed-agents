"""
config/settings.py
------------------
Shared infrastructure config — things every agent in this repo needs.

Agent-specific config (name, model override, token limits, output paths)
lives in each agent's own file (e.g. agents/research_agent.py).
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
}
