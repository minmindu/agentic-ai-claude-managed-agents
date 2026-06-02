# Agentic AI — Claude Managed Agents Examples

A growing collection of practical examples built on the [Anthropic Managed Agents API](https://docs.anthropic.com/en/docs/agents). Each example is self-contained and demonstrates a different agentic pattern — from a single autonomous agent to coordinated multi-agent pipelines.

---

## Examples

### [`research_agent/`](research_agent/)

A single-agent research pipeline that:

1. Spins up a Claude Managed Agent with custom tools (arXiv, Tavily, Wikipedia)
2. Generates a sourced research report on any topic
3. Reflects on and rewrites the report for academic quality
4. Exports the final report as a styled HTML file

See [research_agent/README.md](research_agent/README.md) for setup and usage.

---

## Planned Examples

> More examples will be added over time, including multi-agent architectures.

| Example | Pattern | Status |
|---|---|---|
| `research_agent/` | Single agent with custom tools | ✅ Available |
| *(coming soon)* | Multi-agent with handoffs | 🔜 Planned |
| *(coming soon)* | Supervisor + worker agents | 🔜 Planned |

---

## Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/) with Managed Agents access

A shared `.env.example` lives at the repo root; each example folder contains its own `requirements.txt`. Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
# then edit .env with your API keys
```

---

## Repository Structure

```
agentic-ai-claude-managed-agents/
├── .env.example          # Env template (copy to .env)
├── conftest.py           # pytest path setup (makes packages importable)
├── pytest.ini            # pytest configuration
├── research_agent/       # Single-agent research pipeline
│   ├── main.py
│   ├── requirements.txt
│   ├── agents/           # Session management and agent setup
│   ├── config/           # Centralised settings
│   ├── workflows/        # Report generation, reflection, HTML export, parser
│   ├── tools/            # Tool schemas, implementations, and executor
│   └── tests/            # Unit tests
└── ...                   # Future examples live here as siblings
```
