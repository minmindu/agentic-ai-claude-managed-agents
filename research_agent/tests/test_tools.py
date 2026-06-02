import pytest
from unittest.mock import patch, MagicMock
from tools.research_tools import arxiv_search_tool, tavily_search_tool, wikipedia_search_tool


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

class TestArxivSearchTool:
    def _make_paper(self, title="Test Paper", url="https://arxiv.org/abs/0000.0001"):
        paper = MagicMock()
        paper.title = title
        paper.authors = [MagicMock(name="Author A")]
        paper.published.date.return_value = "2024-01-01"
        paper.summary = "A test abstract that is long enough."
        paper.entry_id = url
        return paper

    def test_returns_structured_results(self):
        paper = self._make_paper()
        with patch("time.sleep"), patch("arxiv.Client") as mock_cls, patch("arxiv.Search"):
            mock_cls.return_value.results.return_value = [paper]
            results = arxiv_search_tool("machine learning", max_results=1)

        assert len(results) == 1
        assert results[0]["title"] == "Test Paper"
        assert results[0]["url"] == "https://arxiv.org/abs/0000.0001"
        assert "summary" in results[0]
        assert "authors" in results[0]
        assert "published" in results[0]

    def test_empty_results_returns_error(self):
        with patch("time.sleep"), patch("arxiv.Client") as mock_cls, patch("arxiv.Search"):
            mock_cls.return_value.results.return_value = []
            results = arxiv_search_tool("xkzq1234nonexistent")

        assert "error" in results[0]

    def test_api_exception_returns_error(self):
        with patch("time.sleep"), patch("arxiv.Client") as mock_cls, patch("arxiv.Search"):
            mock_cls.return_value.results.side_effect = Exception("network failure")
            results = arxiv_search_tool("test query")

        assert "error" in results[0]
        assert "arXiv search failed" in results[0]["error"]

    def test_summary_is_truncated_to_500_chars(self):
        paper = self._make_paper()
        paper.summary = "x" * 1000
        with patch("time.sleep"), patch("arxiv.Client") as mock_cls, patch("arxiv.Search"):
            mock_cls.return_value.results.return_value = [paper]
            results = arxiv_search_tool("test")

        assert len(results[0]["summary"]) <= 500


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------

class TestTavilySearchTool:
    def _mock_response(self, results):
        return {"results": results}

    def test_returns_structured_results(self):
        raw = [{"title": "Article", "url": "https://example.com", "content": "Some content"}]
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
             patch("tavily.TavilyClient") as mock_cls:
            mock_cls.return_value.search.return_value = self._mock_response(raw)
            results = tavily_search_tool("AI news")

        assert len(results) == 1
        assert results[0]["title"] == "Article"
        assert results[0]["url"] == "https://example.com"
        assert "content" in results[0]

    def test_missing_api_key_returns_error(self):
        import os
        env = {k: v for k, v in os.environ.items() if k != "TAVILY_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            results = tavily_search_tool("test")

        assert "error" in results[0]
        assert "TAVILY_API_KEY" in results[0]["error"]

    def test_empty_results_returns_error(self):
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
             patch("tavily.TavilyClient") as mock_cls:
            mock_cls.return_value.search.return_value = self._mock_response([])
            results = tavily_search_tool("obscure query")

        assert "error" in results[0]

    def test_content_is_truncated_to_500_chars(self):
        raw = [{"title": "T", "url": "https://x.com", "content": "y" * 1000}]
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
             patch("tavily.TavilyClient") as mock_cls:
            mock_cls.return_value.search.return_value = self._mock_response(raw)
            results = tavily_search_tool("test")

        assert len(results[0]["content"]) <= 500


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------

class TestWikipediaSearchTool:
    def test_returns_summary_and_source_url(self):
        with patch("wikipedia.summary", return_value="Summary text"), \
             patch("wikipedia.page") as mock_page:
            mock_page.return_value.title = "Artificial Intelligence"
            mock_page.return_value.url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
            result = wikipedia_search_tool("artificial intelligence")

        assert "Artificial Intelligence" in result
        assert "Summary text" in result
        assert "https://en.wikipedia.org" in result

    def test_handles_disambiguation_by_using_first_option(self):
        import wikipedia as wiki
        disambig = wiki.exceptions.DisambiguationError("Python", ["Python (language)", "Python (snake)"])
        with patch("wikipedia.summary", side_effect=[disambig, "Python is a language"]), \
             patch("wikipedia.page") as mock_page:
            mock_page.return_value.title = "Python (language)"
            mock_page.return_value.url = "https://en.wikipedia.org/wiki/Python"
            result = wikipedia_search_tool("Python")

        assert "disambiguation resolved" in result

    def test_handles_page_not_found(self):
        import wikipedia as wiki
        with patch("wikipedia.summary", side_effect=wiki.exceptions.PageError("xkzq")):
            result = wikipedia_search_tool("xkzqwerty12345")

        assert "No Wikipedia page found" in result

    def test_handles_generic_exception(self):
        with patch("wikipedia.summary", side_effect=Exception("network error")):
            result = wikipedia_search_tool("test")

        assert "Wikipedia search error" in result
