"""
main.py
-------
Entrypoint for the research agent pipeline.

Usage:
  python main.py

Or import from another script:
  from main import run_workflow
  result = run_workflow("AI ethics in healthcare")

Production tip — skip re-creation by passing existing IDs:
  run_workflow("AI ethics in healthcare",
               agent_id="agt_01...",
               environment_id="env_01...")
"""

import anthropic


from config.settings import SETTINGS
from agents.research_agent import AGENT_CONFIG, TOOL_MAPPING, create_research_agent
from agents.setup import create_environment
from workflows.report import generate_research_report_with_tools
from workflows.reflection import reflection_and_rewrite
from workflows.html_export import convert_report_to_html

# --- memory ---
import threading
from pymongo.database import Database
from memory.db import get_db, ensure_indexes
from memory.conversation_summary import summarize_session
from memory.context import build_memory_context

def run_workflow(
    topic: str,
    db: Database,  # --- memory ---
    student_id: str | None = None,  # --- memory ---
    output_html: str | None = None,
    agent_id: str | None = None,
    environment_id: str | None = None,
) -> dict:
    """
    Run the full research pipeline end-to-end.

    Args:
        topic:          The research question or topic.
        output_html:    Path to write the HTML report (defaults to settings).
        agent_id:       Existing agent ID to reuse (skips creation if provided).
        environment_id: Existing environment ID to reuse (skips creation if provided).

    Returns:
        Dict with keys: report, reflection, revised, html.
    """
    output_html = output_html or AGENT_CONFIG["default_output_html"]

    print(f"\n{'='*60}")
    print(f"Research topic: {topic}")
    print(f"{'='*60}\n")

    ## --- TODO: hardcode the environment and agentId for testing -----
    agent_id = "agent_01TcfMpQSNuF4UnfV5ciGh4P"
    environment_id = "env_01RWH4KVTgEyAGZzPLKtAPwR"
    print(f"--- Reuse: agent_id={agent_id}, environment_id={environment_id} ---")

    client = anthropic.Anthropic(api_key=SETTINGS["api_key"])

    # ── Setup (skip if IDs supplied) ───────────────────────────────────────
    if not agent_id or not environment_id:
        print("--- Setup: Creating agent and environment ---")
        print("    (Pass agent_id and environment_id to skip this step)\n")

    if not agent_id:
        agent_id = create_research_agent(client)

    if not environment_id:
        environment_id = create_environment(client)


    # ── Step 0: Assemble student memory context (the orchestration boundary),  ─────────────────────────
    #  Either from the student profile or its pass conversation summary
    context_preamble = build_memory_context(db=db, student_id=student_id, topic=topic)
    print(f"\n--- Step 0: Memory context for student_id={student_id} ---")
    print(f"   context_preamble:\n{context_preamble}\n")

    # ── Step 1: Generate report with Managed Agent ─────────────────────────
    # hand the memory context it to the report step — report.py itself just runs the agent.
    
    report, session_id = generate_research_report_with_tools(
        client=client,
        prompt=topic,
        agent_id=agent_id,
        environment_id=environment_id,
        tool_mapping=TOOL_MAPPING,
        db=db,
        student_id=student_id,
        context_preamble=context_preamble,
    )

    ## ── Memory ─────────────────────────
    # Open a thread to summarize the session in the background while we do reflection and HTML conversion.
    print("\n--- Step 1.5: Summarizing sessions and write into a database collection in the background ---")
    ## TEST ONLY    
    # session_id = "sesn_01SnN4ghATHfySwbacX2Trt2"

    summary_thread = threading.Thread(
        target=summarize_session,
        kwargs=dict(client=client, db=db, session_id=session_id, student_id=student_id),
    )
    summary_thread.start()

    ## ── Step 2: Reflect and rewrite ────────────────────────────────────────
    result = reflection_and_rewrite(client=client, report=report)
    print("Reflection:\n", result["reflection"])

    ## ── Step 3: Convert to HTML ────────────────────────────────────────────
    html = convert_report_to_html(client=client, report=result["revised_report"])

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ HTML report saved to: {output_html}")

    return {
        "report":     report,
        "reflection": result["reflection"],
        "revised":    result["revised_report"],
        "html":       html,
    }

# ──────────────────────────────────────────
# Main function
# ──────────────────────────────────────────

if __name__ == "__main__":
    # ── Memory: Get DB handle and ensure indexes ─────────────────────────────
    db = get_db()
    ensure_indexes(db)
    ## TODO: need to get a student_id from the database later, for now just hardcode a test value
    # result = run_workflow( "Radio observations of recurrent novae", db=db, student_id="student123")
    result = run_workflow( "what is agentic ai", db=db, student_id="student456")
    print("\n" + "="*60)
    print("Revised report preview (first 500 chars):")
    print("="*60)
    print(result["revised"][:500])
