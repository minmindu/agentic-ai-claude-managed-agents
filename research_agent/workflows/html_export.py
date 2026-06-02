"""
workflows/html_export.py
------------------------
Step 3: Convert the revised report to a styled HTML document.

Plain Messages API call — no tools or session needed.
"""

import anthropic

from config.settings import SETTINGS
from agents.research_agent import AGENT_CONFIG


def convert_report_to_html(client: anthropic.Anthropic, report: str) -> str:
    """
    Convert a plaintext research report into a well-structured HTML document.

    Args:
        client: Authenticated Anthropic client.
        report: Plain text report (revised version from Step 2).

    Returns:
        Full HTML string ready to write to a file.
    """
    print("\n--- Step 3: Converting to HTML ---")

    user_prompt = f"""
Convert the following research report into a well-structured, clean HTML document.

Requirements:
- Use proper HTML tags: <html>, <head>, <body>, <h1>, <h2>, <p>, <ul>, <li>, etc.
- Make all URLs clickable using <a href="..."> tags.
- Preserve the citation style from the original report.
- Organize content into clearly labeled sections with headers.
- Respond ONLY with valid HTML. Do not include any commentary or markdown fences.

Report:
{report}
"""

    response = client.messages.create(
        model=SETTINGS["default_model"],
        max_tokens=AGENT_CONFIG["html_max_tokens"],
        system="You convert plaintext reports into full clean HTML documents.",
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text.strip()
