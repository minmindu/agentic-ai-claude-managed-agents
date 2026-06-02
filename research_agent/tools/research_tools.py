"""
tools/research_tools.py
-----------------------
Custom tool schemas and implementations for the research agent.

Each tool is defined as a pair:
  - A schema dict (passed to the Managed Agent at creation time)
  - A Python function (called at runtime when the agent invokes the tool)

Adding a new tool:
  1. Add a schema dict and implementation function here.
  2. Register the function in tools/executor.py TOOL_MAPPING.
  3. Add the schema dict to the tools list in agents/research_agent.py.

Required env vars (loaded from .env):
  TAVILY_API_KEY  — sign up at https://tavily.com
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

ARXIV_TOOL_DEF = {
    "type": "custom",
    "name": "arxiv_search_tool",
    "description": (
        "Search arXiv for academic papers. Use this to find scientific papers, preprints, "
        "and research on any topic. Returns paper titles, authors, abstracts, and arXiv URLs. "
        "Prefer this tool when the query is scientific or technical in nature. "
        "Do not use this for general web content — use tavily_search_tool for that."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on arXiv.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 2).",
                "default": 2,
            },
        },
        "required": ["query"],
    },
}


def arxiv_search_tool(query: str, max_results: int = 2) -> list:
    """
    Search academic papers on arXiv and return structured results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.  # hard cap as 2 for lab environment regardless of what Claude requests to avoid hitting arXiv rate limits

    Returns:
        A list of dicts, each with keys: title, authors, published, summary, url.
        On error, returns a list with a single dict containing an "error" key.
    """
    import time
    import arxiv

    time.sleep(10)
    client = arxiv.Client(page_size=min(max_results, 2), delay_seconds=15, num_retries=3)
    search = arxiv.Search(
        query=query,
        max_results=min(max_results, 2),
        sort_by=arxiv.SortCriterion.Relevance,
    )

    results = []
    for attempt in range(3):
        try:
            results = list(client.results(search))
            break
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                time.sleep(20 * (attempt + 1))
            else:
                return [{"error": f"arXiv search failed: {e}"}]

    if not results:
        return [{"error": f"No arXiv results found for: {query}"}]

    return [
        {
            "title":     paper.title,
            "authors":   [a.name for a in paper.authors],
            "published": str(paper.published.date()),
            "summary":   paper.summary[:500].strip(),
            "url":       paper.entry_id,
        }
        for paper in results
    ]


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------

TAVILY_TOOL_DEF = {
    "type": "custom",
    "name": "tavily_search_tool",
    "description": (
        "Search the web using Tavily. Use this to find current news, articles, blog posts, "
        "and general web content. Returns titles, URLs, and content snippets. "
        "Prefer this for non-academic queries or when you need recent information. "
        "For scientific papers, prefer arxiv_search_tool instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 2).",
                "default": 2,
            },
        },
        "required": ["query"],
    },
}


def tavily_search_tool(query: str, max_results: int = 2) -> list:
    """
    Perform a general web search using the Tavily API and return structured results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.

    Returns:
        A list of dicts, each with keys: title, url, content.
        On error, returns a list with a single dict containing an "error" key.
    """
    from tavily import TavilyClient

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return [{"error": "TAVILY_API_KEY is not set. Add it to your .env file (https://tavily.com)."}]

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, max_results=max_results)
    results = response.get("results", [])

    if not results:
        return [{"error": f"No Tavily results found for: {query}"}]

    return [
        {
            "title":   r.get("title", ""),
            "url":     r.get("url", ""),
            "content": r.get("content", "")[:500].strip(),
        }
        for r in results
    ]


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------

WIKIPEDIA_TOOL_DEF = {
    "type": "custom",
    "name": "wikipedia_search_tool",
    "description": (
        "Search Wikipedia for background information on a topic. Use this for definitions, "
        "overviews, historical context, and encyclopaedic summaries. Returns the article "
        "summary and URL. Best used alongside arxiv_search_tool or tavily_search_tool "
        "to provide richer context in research reports."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The topic to look up on Wikipedia.",
            },
        },
        "required": ["query"],
    },
}


def wikipedia_search_tool(query: str) -> str:
    """
    Retrieve a summary from Wikipedia for the given query.

    Args:
        query: The topic or title to look up on Wikipedia.

    Returns:
        A plain-text summary of the Wikipedia article, or an error message.
    """
    import wikipedia

    try:
        summary = wikipedia.summary(query, sentences=10, auto_suggest=True)
        page = wikipedia.page(query, auto_suggest=True)
        return f"**{page.title}**\n\n{summary}\n\nSource: {page.url}"
    except wikipedia.exceptions.DisambiguationError as e:
        try:
            summary = wikipedia.summary(e.options[0], sentences=10)
            page = wikipedia.page(e.options[0])
            return f"**{page.title}** (disambiguation resolved)\n\n{summary}\n\nSource: {page.url}"
        except Exception:
            return f"Disambiguation: try one of {e.options[:5]}"
    except wikipedia.exceptions.PageError:
        return f"No Wikipedia page found for: {query}"
    except Exception as ex:
        return f"Wikipedia search error: {ex}"
