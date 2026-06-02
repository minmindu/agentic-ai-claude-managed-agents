import pytest
from unittest.mock import MagicMock
from workflows.helper.parser import parse_input, strip_markdown_fences


def test_string_returned_unchanged():
    assert parse_input("hello world") == "hello world"


def test_empty_string_returned_unchanged():
    assert parse_input("") == ""


def test_list_of_dicts_joins_assistant_messages():
    messages = [
        {"role": "user", "content": "What is AI?"},
        {"role": "assistant", "content": "AI is..."},
        {"role": "assistant", "content": "...artificial intelligence."},
    ]
    assert parse_input(messages) == "AI is...\n\n...artificial intelligence."


def test_list_of_dicts_skips_non_assistant_roles():
    messages = [
        {"role": "user", "content": "should be ignored"},
        {"role": "assistant", "content": "included"},
    ]
    assert parse_input(messages) == "included"


def test_list_of_objects_joins_assistant_content():
    msg = MagicMock()
    msg.role = "assistant"
    msg.content = "response text"
    assert parse_input([msg]) == "response text"


def test_list_of_objects_skips_non_assistant_roles():
    user_msg = MagicMock()
    user_msg.role = "user"
    user_msg.content = "ignored"

    assistant_msg = MagicMock()
    assistant_msg.role = "assistant"
    assistant_msg.content = "kept"

    assert parse_input([user_msg, assistant_msg]) == "kept"


def test_empty_list_returns_empty_string():
    assert parse_input([]) == ""


def test_non_string_non_list_falls_back_to_str():
    assert parse_input(42) == "42"
    assert parse_input(None) == "None"


# --- strip_markdown_fences ---

def test_no_fences_returned_unchanged():
    assert strip_markdown_fences("plain text") == "plain text"


def test_strips_plain_code_fence():
    assert strip_markdown_fences("```\nhello\n```") == "hello"


def test_strips_json_language_tag():
    assert strip_markdown_fences('```json\n{"key": "value"}\n```') == '{"key": "value"}'


def test_empty_string_returned_unchanged():
    assert strip_markdown_fences("") == ""


def test_strips_fence_without_trailing_fence():
    result = strip_markdown_fences("```json\n{}")
    assert result == "{}"
