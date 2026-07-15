# Research Agent — Claude Managed Agents

A multi-step research pipeline powered by the Anthropic Claude Managed Agents API,
with a MongoDB-backed **memory layer** that persists every session and summarizes it
for later recall.

## What it does

Given a research topic, the pipeline:

1. **Generates a sourced report** — a Managed Agent autonomously decides which tools
   to call (arXiv, Tavily, Wikipedia, plus the built-in web search/fetch toolset) and
   when to stop. Every turn is recorded to MongoDB as it happens.
2. **Reflects and rewrites** — a second pass critiques the draft and produces a
   revised report.
3. **Exports to HTML** — the revised report is converted to a standalone HTML file.

In parallel with steps 2–3, a background thread summarizes the session and stores a
compact, searchable record for future runs.

## Project structure

```
research_agent/
├── config/
│   └── settings.py          # Shared infra config (API key, default model, MongoDB URI/collections)
├── tools/
│   ├── research_tools.py    # Tool schemas + implementations (arXiv, Tavily, Wikipedia)
│   └── executor.py          # Generic tool dispatcher (tool_mapping injected by caller)
├── agents/
│   ├── setup.py             # Generic create_agent() and create_environment()
│   ├── research_agent.py    # Research-specific config, system prompt, tools registry, agent factory
│   └── session.py           # Session management + SSE event loop (records each turn to memory)
├── memory/                  # ---  Memory layer ---
│   ├── db.py                # get_db() connection handle + ensure_indexes()
│   ├── conversation.py      # ConversationRecorder — one document per turn
│   └── conversation_summary.py  # summarize_session() + find_relevant_past_summaries()
├── workflows/
│   ├── report.py            # Step 1: generate_research_report_with_tools()
│   ├── reflection.py        # Step 2: reflection_and_rewrite()
│   ├── html_export.py       # Step 3: convert_report_to_html()
│   └── helper/
│       └── parser.py        # Shared text-processing utilities (parse_input)
├── tests/                   # Unit tests (pytest)
├── main.py                  # Entrypoint — run_workflow()
└── requirements.txt
```

## The memory layer

The memory layer lives in [memory/](memory/) and uses two MongoDB collections:

| Collection             | Granularity        | Retention  | Purpose |
|------------------------|--------------------|------------|---------|
| `conversation`         | One doc per turn   | 90-day TTL | Raw transcript: user messages, assistant messages, tool calls, and tool results. |
| `conversation_summary` | One doc per session| Permanent  | LLM-generated 2–3 sentence summary, extracted topic, open threads, and a deterministic list of `sources_used`. |

Key pieces:

- [memory/conversation.py](memory/conversation.py) — `ConversationRecorder` writes one
  document per turn during a session. Tool-call batches are tagged with a shared
  `group_id` so a call and its result can be correlated.
- [memory/conversation_summary.py](memory/conversation_summary.py) —
  `summarize_session()` reads a completed session's turns, asks Claude for a structured
  JSON summary, stores it, and marks the source turns as `summarized`. `sources_used`
  is built deterministically from successful `tool_result` docs, never from the LLM.
  `find_relevant_past_summaries()` looks up prior sessions for a student (regex fallback
  today; intended to run Atlas hybrid vector + text search in production).
- [memory/db.py](memory/db.py) — one `MongoClient` per process via `get_db()`, plus
  `ensure_indexes()` for the plain collection indexes and TTL. The Atlas Vector/Search
  index that auto-embeds `conversation_summary.summary` must be created separately via
  the Atlas UI or Admin API.

## Setup

From the repo root, copy the shared `.env.example` and fill in your keys:

```bash
cp .env.example .env
# then edit .env with your actual keys
```

Required environment variables:

| Variable            | Required | Default            | Notes |
|---------------------|----------|--------------------|-------|
| `ANTHROPIC_API_KEY` | yes      | —                  | Claude Managed Agents API. |
| `TAVILY_API_KEY`    | yes      | —                  | Web search in `research_tools`. |
| `DATABASE_URI`      | yes      | —                  | Atlas connection string; `get_db()` raises if unset. |
| `DATABASE`          | no       | `ai_memory`   | Database name. |
| `COLLECTION_CONVERSATION` | no | `conversation` | Override only for multi-env / multi-agent namespacing. |
| `COLLECTION_CONVERSATION_SUMMARY` | no | `conversation_summary` | Same. |

Install dependencies:

```bash
cd research_agent
## if using a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
##
pip install -r requirements.txt
pip install -r requirements-dev.txt   # only if you're running the tests
```

## Usage

All commands below must be run from the `research_agent/` directory.

```bash
cd research_agent
python main.py
```

`main.py` opens a MongoDB handle, ensures indexes, and runs the pipeline for a sample
topic. To call it programmatically, pass a `db` handle and a `student_id`:

```python
from memory.db import get_db, ensure_indexes
from main import run_workflow

db = get_db()
ensure_indexes(db)

result = run_workflow(
    "AI ethics in healthcare",
    db=db,
    student_id="student_abc123",
)
# result keys: report, reflection, revised, html
```

## Running tests

The tests exercise the pipeline and the memory layer without a live Atlas cluster
(the memory tests use an in-memory / mocked MongoDB). From the repo root:

```bash
pip install -r research_agent/requirements-dev.txt
pytest research_agent/tests/
```

## Production tip: reuse agent and environment IDs

`run_workflow()` creates a fresh agent and environment on every call by default.
In production, create them once and store their IDs:

```bash
# Run from the research_agent/ directory
python -c "
import anthropic
from config.settings import SETTINGS
from agents.research_agent import create_research_agent
from agents.setup import create_environment
client = anthropic.Anthropic(api_key=SETTINGS['api_key'])
agent_id = create_research_agent(client)
env_id   = create_environment(client)
print(f'AGENT_ID={agent_id}')
print(f'ENVIRONMENT_ID={env_id}')
"
```

Then pass the IDs directly:

```python
run_workflow("AI ethics in healthcare",
             db=db,
             student_id="student_ab12",
             agent_id="agt_01...",
             environment_id="env_01...")
```
