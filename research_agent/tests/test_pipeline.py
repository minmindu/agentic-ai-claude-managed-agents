import json
import pytest
from unittest.mock import MagicMock
from workflows.reflection import reflection_and_rewrite
from workflows.html_export import convert_report_to_html


def _make_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text=response_text)]
    return client


# ---------------------------------------------------------------------------
# reflection_and_rewrite
# ---------------------------------------------------------------------------

class TestReflectionAndRewrite:
    def test_returns_reflection_and_revised_report(self):
        payload = {
            "reflection": "Strengths: clear. Limitations: shallow.",
            "revised_report": "Improved report content.",
        }
        result = reflection_and_rewrite(_make_client(json.dumps(payload)), "Original report.")

        assert result["reflection"] == payload["reflection"]
        assert result["revised_report"] == payload["revised_report"]

    def test_strips_markdown_json_fences(self):
        payload = {"reflection": "Good.", "revised_report": "Better."}
        fenced = f"```json\n{json.dumps(payload)}\n```"
        result = reflection_and_rewrite(_make_client(fenced), "Report.")

        assert result["reflection"] == "Good."
        assert result["revised_report"] == "Better."

    def test_strips_plain_code_fences(self):
        payload = {"reflection": "OK", "revised_report": "Revised."}
        fenced = f"```\n{json.dumps(payload)}\n```"
        result = reflection_and_rewrite(_make_client(fenced), "Report.")

        assert result["reflection"] == "OK"

    def test_raises_value_error_on_invalid_json(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            reflection_and_rewrite(_make_client("not valid json at all"), "Report.")

    def test_passes_report_content_in_prompt(self):
        payload = {"reflection": "x", "revised_report": "y"}
        client = _make_client(json.dumps(payload))
        reflection_and_rewrite(client, "My unique report text.")

        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "My unique report text." in prompt

    def test_missing_keys_return_empty_strings(self):
        result = reflection_and_rewrite(_make_client("{}"), "Report.")

        assert result["reflection"] == ""
        assert result["revised_report"] == ""


# ---------------------------------------------------------------------------
# convert_report_to_html
# ---------------------------------------------------------------------------

class TestConvertReportToHtml:
    def test_returns_html_string_from_model(self):
        expected = "<html><body><p>Report</p></body></html>"
        result = convert_report_to_html(_make_client(expected), "Plain text report.")

        assert result == expected

    def test_passes_report_content_in_prompt(self):
        client = _make_client("<html/>")
        convert_report_to_html(client, "Unique report content here.")

        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Unique report content here." in prompt

    def test_uses_configured_max_tokens(self):
        from agents.research_agent import AGENT_CONFIG
        client = _make_client("<html/>")
        convert_report_to_html(client, "Report.")

        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == AGENT_CONFIG["html_max_tokens"]
