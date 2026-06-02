"""
tools/executor.py
-----------------
Generic dispatcher: executes a named tool from a caller-supplied mapping.

The tool mapping is owned by each agent (e.g. agents/research_agent.py)
and passed in at call time — this module has no knowledge of any specific agent.
"""

import json


def execute_tool(
    tool_name: str,
    tool_input: dict,
    tool_mapping: dict[str, callable],
) -> str:
    """
    Execute a custom tool by name and return its result as a JSON string.

    Args:
        tool_name:    The name of the tool to call.
        tool_input:   The input dict provided by Claude.
        tool_mapping: Name → callable map supplied by the calling agent.

    Returns:
        A JSON-encoded string suitable for the `user.custom_tool_result` event.
    """
    if tool_name not in tool_mapping:
        result = {"error": f"Unknown tool: {tool_name!r}. "
                           f"Available: {list(tool_mapping.keys())}"}
        return json.dumps(result)

    try:
        result = tool_mapping[tool_name](**tool_input)
    except TypeError as e:
        result = {"error": f"Tool call failed (bad arguments): {e}"}
    except Exception as e:
        result = {"error": f"Tool execution error: {e}"}

    return json.dumps(result)
