# Research Agent — Claude Managed Agents

A multi-step research pipeline powered by the Anthropic Claude Managed Agents API,
with a MongoDB-backed **memory layer** that personalizes each session, remembers what
a student has researched before, and accumulates reusable findings across everyone.

## What it does

Given a research topic (and a `student_id`), the pipeline:

1. **Primes the session with memory** — before the agent runs, it assembles context for
   this student and injects it as a per-session **system override**: their profile (how
   to talk to them) plus relevant past-session summaries (what you've already covered),
   filtered by a similarity-score threshold so an irrelevant match never reaches the prompt.
2. **Generates a sourced report** — a Managed Agent autonomously decides which tools to
   call (arXiv, Tavily, Wikipedia, plus the built-in web search/fetch toolset) and when to
   stop. Every turn is recorded to MongoDB as it happens.
3. **Reflects and rewrites** — a second pass critiques the draft and produces a revised report.
4. **Exports to HTML** — the revised report is converted to a standalone HTML file.

In parallel with the reflection/HTML steps, a background thread summarizes the session and
stores a compact, vector-searchable record for future runs.

## Project structure

```
research_agent/
├── config/
│   └── settings.py          # Shared infra config (API keys, model, MongoDB, embeddings, vector indexes)
├── tools/
│   ├── research_tools.py    # Tool schemas + implementations (arXiv, Tavily, Wikipedia)
│   └── executor.py          # Generic tool dispatcher (tool_mapping injected by caller)
├── agents/
│   ├── setup.py             # Generic create_agent() and create_environment()
│   ├── research_agent.py    # Research-specific config, SYSTEM_PROMPT, tools registry, agent factory
│   └── session.py           # Session mgmt + SSE event loop; records each turn; applies system override
├── memory/                  # --- Memory layer (4 collections) ---
│   ├── db.py                # get_db() connection handle + ensure_indexes()
│   ├── embeddings.py        # embed_text()/embed_texts() — Voyage AI wrapper (document vs query)
│   ├── conversation.py      # ConversationRecorder — one document per turn
│   ├── conversation_summary.py  # summarize_session(), find_relevant_past_summaries(), format_summaries_as_context()
│   ├── knowledge_base.py    # KnowledgeBaseStore — global, cross-student findings (vector search)
│   └── student.py           # StudentStore — one upserted doc per student (personalization state)
├── workflows/
│   ├── report.py            # Step 1: build_memory_context() + generate_research_report_with_tools()
│   ├── reflection.py        # Step 2: reflection_and_rewrite()
│   ├── html_export.py       # Step 3: convert_report_to_html()
│   └── helper/
│       └── parser.py        # Shared text-processing utilities (parse_input)
├── script/
│   └── seed_students.py     # Seed the `student` collection with example profiles
├── tests/                   # Unit tests (pytest; memory tests use a mocked MongoDB)
├── main.py                  # Entrypoint — run_workflow()
└── requirements.txt
```

## The memory layer

The memory layer lives in [memory/](memory/) and uses four MongoDB collections:

| Collection             | Scope        | Granularity         | Retention  | Vector? | Purpose |
|------------------------|--------------|---------------------|------------|---------|---------|
| `conversation`         | Per student  | One doc per turn    | 90-day TTL | No      | Raw transcript: user/assistant messages, tool calls, and tool results. |
| `conversation_summary` | Per student  | One doc per session | Permanent  | Yes     | Structured summary, topic, open thread, deterministic `sources_used`, and a `summary_embedding`. |
| `knowledge_base`       | Global       | One doc per finding | Permanent  | Yes     | Reusable findings any student can benefit from; `content` + `content_embedding`. |
| `student`              | Per student  | One doc per student | Permanent  | No      | Personalization state (academic level, register, interests, notes), upserted in place. |

Each file's module docstring documents its exact document schema.

Key pieces:

- **Write path** — [memory/conversation.py](memory/conversation.py) `ConversationRecorder`
  writes one document per turn during a session. Tool-call batches share a `group_id` so a
  call and its result can be correlated.
- **Summarize** — [memory/conversation_summary.py](memory/conversation_summary.py)
  `summarize_session()` reads a completed session's turns, asks Claude for a **structured
  summary via tool use** (no fragile JSON-string parsing), embeds `topic + summary` with
  Voyage, stores it, and marks the source turns as `summarized`. `sources_used` is built
  deterministically from successful `tool_result` docs, never from the LLM.
- **Read path** — `find_relevant_past_summaries()` runs a student-scoped Atlas
  `$vectorSearch` (regex fallback when `vector=False`), then drops any hit below
  `MEMORY_MIN_SIMILARITY_SCORE`. `format_summaries_as_context()` turns the survivors into
  a text block. [workflows/report.py](workflows/report.py) `build_memory_context()`
  combines that with the student profile and hands it to `run_session`, which composes it
  with the base system prompt and applies it as a **per-session system override**.
- **Knowledge base** — [memory/knowledge_base.py](memory/knowledge_base.py)
  `KnowledgeBaseStore` appends global findings and retrieves them by meaning
  (`search_knowledge_base()`), also score-thresholded.
- **Embeddings** — [memory/embeddings.py](memory/embeddings.py) is the one place text
  becomes a vector (Voyage AI). Write side uses `input_type="document"`, read side
  `input_type="query"`. The client is created lazily, so importing never requires a key —
  only actually embedding does (the regex fallbacks and tests run with no `VOYAGE_API_KEY`).
- **Indexes** — [memory/db.py](memory/db.py) opens one `MongoClient` per process via
  `get_db()` and creates the plain collection indexes + the 90-day TTL in
  `ensure_indexes()`. The Atlas **Vector Search** indexes over
  `conversation_summary.summary_embedding` and `knowledge_base.content_embedding` are
  Search-index resources created separately (Atlas UI / Admin API); their names and the
  embedding dimensions live in `config/settings.py`.

## Setup

From the repo root, copy the shared `.env.example` and fill in your keys:

```bash
cp .env.example .env
# then edit .env with your actual keys
```

Environment variables:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | Claude Managed Agents API. |
| `TAVILY_API_KEY` | yes | — | Web search in `research_tools`. |
| `DATABASE_URI` | yes | — | Atlas connection string; `get_db()` raises if unset. |
| `VOYAGE_API_KEY` | for vector memory | — | Needed for the `$vectorSearch` read paths and for embedding on write. Regex-fallback lookups (`vector=False`) and the tests don't need it. |
| `DATABASE` | no | `research_agent` | Database name. |
| `COLLECTION_CONVERSATION` | no | `conversation` | Override only for multi-env / multi-agent namespacing. |
| `COLLECTION_CONVERSATION_SUMMARY` | no | `conversation_summary` | Same. |
| `COLLECTION_KNOWLEDGE_BASE` | no | `knowledge_base` | Same. |
| `COLLECTION_STUDENT` | no | `student` | Same. |
| `VOYAGE_EMBEDDING_MODEL` | no | `voyage-3.5` | Must match the dimension below and your Atlas index. |
| `VOYAGE_EMBEDDING_DIMS` | no | `1024` | Output dimensionality; must match the vector index's `numDimensions`. |
| `VECTOR_INDEX_CONVERSATION_SUMMARY` | no | `conversation_summary_vector_index` | Name of the Atlas Search index. |
| `VECTOR_INDEX_KNOWLEDGE_BASE` | no | `knowledge_base_vector_index` | Name of the Atlas Search index. |
| `MEMORY_MIN_SIMILARITY_SCORE` | no | `0.7` | Similarity cutoff for injecting a past summary/KB hit. Calibrate to your index's metric; `0.0` disables filtering. |

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

## Seeding data

The memory layer is only useful once there's something to remember. The one store you
seed by hand is `student` — the per-student personalization profiles that get injected
into the system prompt. Until a student has a row,
`StudentStore.personalization_context()` returns `None` and the agent falls back to its
default voice regardless of who's asking.

[script/seed_students.py](script/seed_students.py) is the **write side** of the student
store. It upserts two contrasting demo profiles so the difference is visible:

| `student_id` | `academic_level` | `register` | Resulting voice |
|---|---|---|---|
| `student123` | postgraduate | academic | Dense, primary-source, precise terminology. |
| `student456` | kid | simple | Plain words and everyday analogies, minimal jargon. |

Run it from the `research_agent/` directory:

```bash
python script/seed_students.py
```

Notes:

- **Only `DATABASE_URI` is required** — the `student` collection has no embeddings, so no
  `VOYAGE_API_KEY` or `ANTHROPIC_API_KEY` is needed to seed.
- **Idempotent** — `upsert` keys on `student_id`, so re-running updates the same two rows
  rather than creating duplicates.
- In a real product these rows would come from a signup form / SIS import / an onboarding
  turn; the script just stands in for that data source.

The other memory collections (`conversation`, `conversation_summary`, `knowledge_base`)
are **not** seeded — they populate themselves as the agent runs and summarizes sessions.

> Convention: runnable seeders live in the scripts folder; the DB access code lives in
> [memory/](memory/). If the seed rows outgrow being hardcoded, move them into a
> `data/` folder (e.g. `data/students.json`) and have the script load from it.

## Usage

All commands below must be run from the `research_agent/` directory. Seed the student
profiles first (see [Seeding data](#seeding-data)), then run the pipeline:

```bash
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
(the memory tests use an in-memory / mocked MongoDB and the regex fallbacks, so no
`VOYAGE_API_KEY` is required). From the repo root:

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
