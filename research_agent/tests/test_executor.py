import json
import pytest
from tools.executor import execute_tool

_SAMPLE_MAPPING = {
    "echo_tool":   lambda query: {"echo": query},
    "strict_tool": lambda required_arg: required_arg,
}


def test_unknown_tool_returns_error():
    result = json.loads(execute_tool("nonexistent_tool", {}, _SAMPLE_MAPPING))
    assert "error" in result
    assert "nonexistent_tool" in result["error"]


def test_unknown_tool_lists_available_tools():
    result = json.loads(execute_tool("nonexistent_tool", {}, _SAMPLE_MAPPING))
    for name in _SAMPLE_MAPPING:
        assert name in result["error"]


def test_known_tool_returns_json_encoded_result():
    mapping = {"echo_tool": lambda query: {"echo": query}}
    result = json.loads(execute_tool("echo_tool", {"query": "hello"}, mapping))
    assert result == {"echo": "hello"}


def test_bad_arguments_returns_error():
    mapping = {"strict_tool": lambda required_arg: required_arg}
    result = json.loads(execute_tool("strict_tool", {}, mapping))
    assert "error" in result
    assert "bad arguments" in result["error"]


def test_tool_runtime_exception_returns_error():
    def failing_tool(**kwargs):
        raise ValueError("something went wrong")

    result = json.loads(execute_tool("bad_tool", {}, {"bad_tool": failing_tool}))
    assert "error" in result
    assert "something went wrong" in result["error"]


def test_result_is_always_valid_json():
    raw = execute_tool("does_not_exist", {}, {})
    assert isinstance(json.loads(raw), dict)
