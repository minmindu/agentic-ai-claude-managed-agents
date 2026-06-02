"""
agents/setup.py
---------------
Generic one-time provisioning of a Managed Agent and cloud environment.

These functions are agent-agnostic — they accept all configuration as
arguments so they can be reused across different agents.

In production: call these once, persist the returned IDs (e.g. in env vars
or a config file), and pass them directly to run_workflow() to skip
re-creation on every run.
"""

import anthropic

from config.settings import SETTINGS



def create_environment(client: anthropic.Anthropic) -> str:
    """
    Create a cloud container environment for agent sessions.

    Returns:
        The environment ID string.
    """
    environment = client.beta.environments.create(
        name=SETTINGS["environment_name"],
        config={
            "type": "cloud",
            "networking": {"type": "unrestricted"},
        },
    )
    print(f"✅ Environment created: {environment.id}")
    return environment.id


## This is the main agent factory function
## it can be called by any agent-specific setup function (e.g. create_research_agent) to create an agent with custom config and tools, without duplicating the actual API call logic.
def create_agent(
    client: anthropic.Anthropic,
    name: str,
    model: str,
    system: str,
    tools: list,
) -> str:
    """
    Create a reusable Managed Agent with the given configuration.

    Args:
        client: Authenticated Anthropic client.
        name:   Display name for the agent.
        model:  Claude model ID to use.
        system: System prompt that defines the agent's behaviour.
        tools:  List of tool dicts (built-in and/or custom).

    Returns:
        The agent ID string.
    """
    agent = client.beta.agents.create(
        name=name,
        model=model,
        system=system,
        tools=tools,
    )
    print(f"✅ Agent created: {agent.id}")
    return agent.id
