"""
workflows/reflection.py
-----------------------
Step 2: Reflect on the report and produce a revised version.

Uses the plain Messages API (no tools, no session) — a single synchronous
call is all that's needed here. This matches the original script's approach.
"""

import json
import anthropic

from config.settings import SETTINGS
from agents.research_agent import AGENT_CONFIG
from workflows.helper.parser import strip_markdown_fences


def reflection_and_rewrite(client: anthropic.Anthropic, report: str) -> dict:
    """
    Generate a structured reflection and a revised version of the report.

    Args:
        client: Authenticated Anthropic client.
        report: Plain text report from Step 1.

    Returns:
        Dict with keys:
          "reflection"     — strengths, limitations, suggestions, opportunities
          "revised_report" — improved version of the report
    """
    print("\n--- Step 2: Reflecting and rewriting ---")

    if not report or not report.strip():
        raise ValueError(
            "Step 1 produced an empty report. "
            "Check that the agent session is returning text before running reflection."
        )

    # 1 token ≈ 4 chars; 1 word ≈ 5 chars → 1 word ≈ 1.25 tokens.
    # Reserve 1 000 tokens for reflection + JSON overhead; the rest goes to
    # the revised report. Also cap at the original word count — no need to expand.
    report_words = len(report) // 5
    max_words = min(report_words, int((AGENT_CONFIG["reflection_max_tokens"] - 1000) / 1.25))

    user_prompt = f"""
You are given the following research report:

{report}

Please analyze it and respond ONLY with valid JSON in this exact format:
{{
    "reflection": "Strengths: ...\\nLimitations: ...\\nSuggestions: ...\\nOpportunities: ...",
    "revised_report": "..."
}}

Rules:
- The reflection must cover: Strengths, Limitations, Suggestions, and Opportunities.
- The revised_report should incorporate the reflection to improve clarity and academic tone.
- The revised_report MUST be at most {max_words} words. Cut detail, not accuracy.
- Do not include any text outside the JSON.
"""

    response = client.messages.create(
        model=SETTINGS["default_model"],
        max_tokens=AGENT_CONFIG["reflection_max_tokens"],
        system="You are an academic reviewer and editor.",
        messages=[{"role": "user", "content": user_prompt}],
    )

    llm_output = response.content[0].text.strip()

    llm_output = strip_markdown_fences(llm_output)

    try:
        data = json.loads(llm_output)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Reflection step returned invalid JSON: {e}\n\nRaw output:\n{llm_output}"
        ) from e

    return {
        "reflection":     str(data.get("reflection", "")).strip(),
        "revised_report": str(data.get("revised_report", "")).strip(),
    }
