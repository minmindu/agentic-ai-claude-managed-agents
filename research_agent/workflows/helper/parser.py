"""
workflows/helper/parser.py
--------------------------
Text-processing utilities shared across workflow steps.
"""


def parse_input(report) -> str:
    """
    Accept either a plain-text report string or a messages list from the
    tool-calling loop, and return a single plain-text string.
    """
    if isinstance(report, str):
        return report

    if isinstance(report, list):
        parts = []
        for msg in report:
            if isinstance(msg, dict):
                if msg.get("role") == "assistant" and msg.get("content"):
                    parts.append(msg["content"])
            elif hasattr(msg, "role") and msg.role == "assistant" and msg.content:
                parts.append(msg.content)
        return "\n\n".join(parts)

    return str(report)


def strip_markdown_fences(text: str) -> str:
    """
    Remove ```...``` code fences from model output, including any language tag.
    It seems Claude often wraps JSON responses in ```json ... ``` fences for readability even when the prompt asks for plain output. 
    This strips those fences so the result can be parsed directly.

    Hence, need to remove the extra characters for a valid JSON parsing.
    """
    if not text.startswith("```"):
        return text
    parts = text.split("```")
    inner = parts[1] if len(parts) > 1 else parts[0]
    if inner.startswith("json"):
        inner = inner[4:]
    return inner.strip()
