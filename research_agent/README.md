# Research Agent — Claude Managed Agents

A multi-step research pipeline powered by the Anthropic Claude Managed Agents API.

## Project structure

```
research_agent/
├── config/
│   └── settings.py          # Shared infrastructure config (API key, default model, environment)
├── tools/
│   ├── research_tools.py    # Tool schemas + implementations (arXiv, Tavily, Wikipedia)
│   └── executor.py          # Generic tool dispatcher (tool_mapping injected by caller)
├── agents/
│   ├── setup.py             # Generic create_agent() and create_environment()
│   ├── research_agent.py    # Research-specific config, tools registry, and agent factory
│   └── session.py           # Session management + SSE event loop
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

## Setup

From the repo root, copy the shared `.env.example` and fill in your API keys:

```bash
cp .env.example .env
# then edit .env with your actual keys
```

Install dependencies:

```bash
cd research_agent
pip install -r requirements.txt
```

## Usage

All commands below must be run from the `research_agent/` directory.

```bash
cd research_agent
python main.py
```

Or import and call programmatically:

```python
from main import run_workflow
result = run_workflow("AI ethics in healthcare")
```

## Running tests

From the repo root:

```bash
pip install pytest
pytest
```

Or run only this example's tests directly:

```bash
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
             agent_id="agt_01...",
             environment_id="env_01...")
```
