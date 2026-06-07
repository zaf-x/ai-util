"""Tests for the Agent class (lifecycle, hooks, persistence, tool management)."""

import json
import os
import tempfile
from unittest.mock import Mock
from ai_util import Agent, AIBot, Tools


def _make_agent(**kwargs) -> Agent:
    """Create an Agent with a mock AIBot for testing."""
    bot = AIBot(api_key="test-key", model="test-model")
    tools = Tools()
    return Agent(bot, tools, **kwargs)


class TestAgentLifecycle:
    def test_reset_preserves_system_prompt(self):
        agent = _make_agent()
        agent.bot.messages = [
            {"role": "system", "content": "You are a bot."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        agent.reset()
        assert len(agent.bot.messages) == 1
        assert agent.bot.messages[0] == {"role": "system", "content": "You are a bot."}

    def test_reset_without_system_prompt(self):
        agent = _make_agent()
        agent.bot.messages = [
            {"role": "user", "content": "Hi"},
        ]
        agent.reset()
        assert agent.bot.messages == []

    def test_set_system_prompt_replaces_existing(self):
        agent = _make_agent()
        agent.bot.messages = [{"role": "system", "content": "Old prompt"}]
        agent.set_system_prompt("New prompt")
        assert agent.bot.messages[0]["content"] == "New prompt"

    def test_set_system_prompt_adds_if_missing(self):
        agent = _make_agent()
        agent.bot.messages = []
        agent.set_system_prompt("New prompt")
        assert agent.bot.messages == [{"role": "system", "content": "New prompt"}]

    def test_history_returns_copy(self):
        agent = _make_agent()
        agent.bot.messages = [{"role": "user", "content": "Hi"}]
        h = agent.history()
        h.append({"role": "user", "content": "Extra"})
        assert len(agent.bot.messages) == 1  # original unchanged


class TestAgentHooks:
    def test_on_message_hook_fires_on_send_msg(self, monkeypatch):
        hook = Mock()
        agent = _make_agent(on_message=hook)
        monkeypatch.setattr(
            agent.bot, "send_msg_with_tools",
            lambda msg, tools: {"content": "Hello!", "finish_reason": "stop",
                                 "tool_rounds": 0},
        )
        agent.send_msg("Hi")
        hook.assert_called_once()
        assert hook.call_args[0][0]["role"] == "assistant"
        assert hook.call_args[0][0]["content"] == "Hello!"

    def test_on_error_hook_fires_on_max_rounds(self, monkeypatch):
        """send_msg fires on_error when finish_reason is max_rounds."""
        hook = Mock()
        agent = _make_agent(on_error=hook, on_message=Mock())
        monkeypatch.setattr(
            agent.bot, "send_msg_with_tools",
            lambda msg, tools: {"content": "Max rounds reached.",
                                 "finish_reason": "max_rounds", "tool_rounds": 10},
        )
        agent.send_msg("Hi")
        hook.assert_called_once()
        # on_message should NOT fire on max_rounds
        assert agent.on_message.call_count == 0

    def test_on_tool_call_hook_fires_on_stream(self, monkeypatch):
        hook = Mock()
        agent = _make_agent(on_tool_call=hook)

        def fake_stream(msg, defs, executor):
            yield {
                "type": "tool_call",
                "data": {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "北京"}'},
                },
            }
            yield {"type": "tool_result", "data": {"name": "get_weather",
                                                     "result": "晴"}}
            yield {"type": "done", "data": "Done"}

        monkeypatch.setattr(agent.bot, "stream_output", fake_stream)
        list(agent.stream_msg("Hi"))
        hook.assert_called_once_with("get_weather", '{"city": "北京"}')

    def test_on_tool_result_hook_fires(self, monkeypatch):
        hook = Mock()
        agent = _make_agent(on_tool_result=hook)

        def fake_stream(msg, defs, executor):
            yield {
                "type": "tool_call",
                "data": {
                    "id": "call_1", "type": "function",
                    "function": {"name": "get_weather", "arguments": "{}"},
                },
            }
            yield {"type": "tool_result", "data": {"name": "get_weather",
                                                     "result": "晴"}}
            yield {"type": "done", "data": "Done"}

        monkeypatch.setattr(agent.bot, "stream_output", fake_stream)
        list(agent.stream_msg("Hi"))
        hook.assert_called_once_with("get_weather", "晴")

    def test_on_error_hook_fires_on_stream(self, monkeypatch):
        hook = Mock()
        agent = _make_agent(on_error=hook)

        def fake_stream(msg, defs, executor):
            yield {"type": "error", "data": "Something went wrong"}

        monkeypatch.setattr(agent.bot, "stream_output", fake_stream)
        list(agent.stream_msg("Hi"))
        hook.assert_called_once_with("Something went wrong")

    def test_on_message_hook_fires_on_stream_done(self, monkeypatch):
        hook = Mock()
        agent = _make_agent(on_message=hook)

        def fake_stream(msg, defs, executor):
            yield {"type": "done", "data": "Final answer"}

        monkeypatch.setattr(agent.bot, "stream_output", fake_stream)
        list(agent.stream_msg("Hi"))
        hook.assert_called_once()
        assert hook.call_args[0][0] == {
            "role": "assistant", "content": "Final answer"
        }


class TestAgentPersistence:
    def test_export_import_roundtrip(self):
        agent = _make_agent()
        agent.bot.messages = [
            {"role": "system", "content": "You are a bot."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        agent.bot.model = "gpt-4"
        agent.bot.temperature = 0.5

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            tmp_path = f.name

        try:
            agent.export_history(tmp_path)

            agent2 = _make_agent()
            agent2.import_history(tmp_path)

            assert len(agent2.bot.messages) == 3
            assert agent2.bot.messages[0]["role"] == "system"
            assert agent2.bot.messages[0]["content"] == "You are a bot."
            assert agent2.bot.messages[1] == {"role": "user", "content": "Hi"}
            assert agent2.bot.messages[2] == {"role": "assistant",
                                               "content": "Hello"}
            assert agent2.bot.model == "gpt-4"
            assert agent2.bot.temperature == 0.5
        finally:
            os.unlink(tmp_path)

    def test_import_empty_messages(self):
        agent = _make_agent()
        data = {"version": 1, "messages": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            agent.import_history(tmp_path)
            assert agent.bot.messages == []
        finally:
            os.unlink(tmp_path)

    def test_import_invalid_json_raises(self):
        agent = _make_agent()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            f.write("not json")
            tmp_path = f.name

        try:
            import pytest
            with pytest.raises(ValueError, match="Invalid conversation file"):
                agent.import_history(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_import_unsupported_version_raises(self):
        agent = _make_agent()
        data = {"version": 999, "messages": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            import pytest
            with pytest.raises(ValueError, match="Unsupported conversation version"):
                agent.import_history(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_import_missing_file_raises(self):
        agent = _make_agent()
        import pytest
        with pytest.raises(ValueError, match="Invalid conversation file"):
            agent.import_history("/nonexistent/path.json")


class TestAgentToolManagement:
    def test_add_tool_decorator(self):
        agent = _make_agent()
        @agent.add_tool
        def my_tool(x: int) -> str:
            """Test tool"""
            return str(x)
        assert "my_tool" in agent.tools
        assert agent.tools.execute("my_tool", {"x": 42}) == "42"

    def test_add_tool_with_name(self):
        agent = _make_agent()
        @agent.add_tool(name="renamed", description="Custom name")
        def my_tool(x: int) -> str:
            return str(x)
        assert "renamed" in agent.tools
        assert "my_tool" not in agent.tools

    def test_remove_tool(self):
        agent = _make_agent()
        @agent.add_tool
        def my_tool(x: int) -> str:
            return str(x)
        assert "my_tool" in agent.tools
        agent.remove_tool("my_tool")
        assert "my_tool" not in agent.tools
