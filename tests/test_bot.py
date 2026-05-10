"""Tests for AIBot class (mocked OpenAI client)"""

from unittest.mock import MagicMock, patch

import pytest

from ai_util import AIBot


@pytest.fixture
def mock_openai():
    """Mock OpenAI 客户端，返回 (class_mock, client_mock)"""
    with patch("ai_util.bot.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        yield MockOpenAI, mock_client


class TestAIBotInit:
    """测试初始化"""

    def test_basic_init(self, mock_openai):
        MockOpenAI, _ = mock_openai
        bot = AIBot(api_key="test-key", model="gpt-4o")
        assert bot.model == "gpt-4o"
        assert len(bot.messages) == 0
        MockOpenAI.assert_called_once_with(api_key="test-key")

    def test_init_with_system_prompt(self, mock_openai):
        _, mock_client = mock_openai
        bot = AIBot(api_key="test-key", system_prompt="You are a helper")
        assert len(bot.messages) == 1
        assert bot.messages[0]["role"] == "system"
        assert bot.messages[0]["content"] == "You are a helper"
        # 确保 client 是用传的 key 创建的
        assert bot.client is mock_client

    def test_init_with_base_url(self, mock_openai):
        MockOpenAI, _ = mock_openai
        AIBot(api_key="test-key", base_url="https://custom.api.com")
        MockOpenAI.assert_called_with(
            api_key="test-key", base_url="https://custom.api.com"
        )

    def test_max_tool_rounds(self, mock_openai):
        bot = AIBot(api_key="test-key", max_tool_rounds=5)
        assert bot.max_tool_rounds == 5


class TestAIBotCore:
    """测试核心方法"""

    def _setup_mock_response(self, mock_client, content, tool_calls=None, finish_reason="stop"):
        """辅助方法：配置 mock 响应"""
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_choice.message.tool_calls = tool_calls
        mock_choice.finish_reason = finish_reason

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        return mock_response

    def test_send_msg(self, mock_openai):
        _, mock_client = mock_openai
        self._setup_mock_response(mock_client, "你好！")

        bot = AIBot(api_key="test-key")
        result = bot.send_msg("Hello")

        assert result["content"] == "你好！"
        assert result["finish_reason"] == "stop"
        assert result["tool_calls"] is None
        assert len(bot.messages) == 2  # user + assistant

    def test_send_msg_with_tool_calls(self, mock_openai):
        _, mock_client = mock_openai

        mock_tc = MagicMock()
        mock_tc.id = "call_123"
        mock_tc.function.name = "get_weather"
        mock_tc.function.arguments = '{"city": "北京"}'

        self._setup_mock_response(
            mock_client,
            content=None,
            tool_calls=[mock_tc],
            finish_reason="tool_calls",
        )

        bot = AIBot(api_key="test-key")
        result = bot.send_msg("天气咋样？")

        assert result["content"] is None
        assert result["finish_reason"] == "tool_calls"
        assert result["tool_calls"] is not None

    def test_reset(self, mock_openai):
        bot = AIBot(api_key="test-key", system_prompt="你好")
        bot.messages.append({"role": "user", "content": "hi"})
        bot.messages.append({"role": "assistant", "content": "hello"})
        assert len(bot.messages) == 3

        bot.reset()
        assert len(bot.messages) == 1  # 只保留 system
        assert bot.messages[0]["role"] == "system"

    def test_history(self, mock_openai):
        bot = AIBot(api_key="test-key", system_prompt="你好")
        bot.messages.append({"role": "user", "content": "test"})

        history = bot.history
        assert len(history) == 2
        # 确认是深拷贝
        history.append({"role": "assistant", "content": "haha"})
        assert len(bot.messages) == 2  # 原对象不受影响


class TestAIBotStream:
    """测试流式方法"""

    def test_stream_output_content_only(self, mock_openai):
        _, mock_client = mock_openai

        # 模拟流式响应（只有文本）
        class Chunk:
            def __init__(self, content):
                self.choices = [
                    MagicMock(delta=MagicMock(content=content, tool_calls=None))
                ]

        class Stream:
            def __init__(self):
                self._chunks = [
                    Chunk("你好"),
                    Chunk("世界"),
                    Chunk(None),
                ]
                self._i = 0

            def __iter__(self):
                return self

            def __next__(self):
                if self._i >= len(self._chunks):
                    raise StopIteration
                c = self._chunks[self._i]
                self._i += 1
                return c

        mock_client.chat.completions.create.return_value = Stream()

        bot = AIBot(api_key="test-key")
        events = list(bot.stream_output("Hello"))

        contents = [e for e in events if e["type"] == "content"]
        assert len(contents) == 2
        assert contents[0]["data"] == "你好"
        assert contents[1]["data"] == "世界"

        dones = [e for e in events if e["type"] == "done"]
        assert len(dones) == 1
        assert dones[0]["data"] == "你好世界"


class TestAIBotInternals:
    """测试内部方法"""

    def test_package_tool_calls(self, mock_openai):
        bot = AIBot(api_key="test-key")

        mock_tc = MagicMock()
        mock_tc.id = "call_456"
        mock_tc.function.name = "search"
        mock_tc.function.arguments = '{"q": "test"}'

        packed = bot._package_tool_calls([mock_tc])
        assert packed is not None
        assert packed[0]["id"] == "call_456"
        assert packed[0]["function"]["name"] == "search"
        assert packed[0]["function"]["arguments"] == '{"q": "test"}'

    def test_package_tool_calls_empty(self, mock_openai):
        bot = AIBot(api_key="test-key")
        assert bot._package_tool_calls(None) is None
        assert bot._package_tool_calls([]) is None

    def test_build_kwargs(self, mock_openai):
        bot = AIBot(api_key="test-key")

        kwargs = bot._build_kwargs()
        assert kwargs["model"] == "gpt-4o"
        assert "tools" not in kwargs

        kwargs2 = bot._build_kwargs(
            tools=[{"type": "function"}],
            stream=True,
        )
        assert kwargs2["tools"] == [{"type": "function"}]
        assert kwargs2["stream"] is True
        assert kwargs2["stream_options"] == {"include_usage": True}
