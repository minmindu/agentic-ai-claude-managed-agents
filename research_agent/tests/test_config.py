import pytest
from config.settings import SETTINGS
from agents.research_agent import AGENT_CONFIG


# ---------------------------------------------------------------------------
# Shared global settings
# ---------------------------------------------------------------------------

def test_settings_has_required_keys():
    for key in ("api_key", "default_model", "environment_name"):
        assert key in SETTINGS, f"Missing key in SETTINGS: {key}"


def test_default_model_is_non_empty_string():
    assert isinstance(SETTINGS["default_model"], str) and SETTINGS["default_model"]


def test_environment_name_is_non_empty_string():
    assert isinstance(SETTINGS["environment_name"], str) and SETTINGS["environment_name"]


# ---------------------------------------------------------------------------
# Research-agent-specific config
# ---------------------------------------------------------------------------

def test_agent_config_has_required_keys():
    for key in ("name", "model", "reflection_max_tokens", "html_max_tokens", "default_output_html"):
        assert key in AGENT_CONFIG, f"Missing key in AGENT_CONFIG: {key}"


def test_agent_config_token_limits_are_positive():
    assert AGENT_CONFIG["reflection_max_tokens"] > 0
    assert AGENT_CONFIG["html_max_tokens"] > 0


def test_agent_config_model_is_non_empty_string():
    assert isinstance(AGENT_CONFIG["model"], str) and AGENT_CONFIG["model"]


def test_agent_config_default_output_html_ends_with_html():
    assert isinstance(AGENT_CONFIG["default_output_html"], str)
    assert AGENT_CONFIG["default_output_html"].endswith(".html")
