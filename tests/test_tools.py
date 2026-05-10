"""Tests for Tools and Tool classes (no API key needed)"""

from ai_util import Tools, Tool


class TestTools:
    """测试 Tools 工具集"""

    def test_basic_registration(self):
        tools = Tools()

        @tools.add
        def hello(name: str) -> str:
            """Say hello"""
            return f"Hello {name}"

        assert len(tools) == 1
        assert "hello" in tools
        assert tools.get("hello") is not None

    def test_execute(self):
        tools = Tools()

        @tools.add
        def add(a: int, b: int = 0) -> int:
            """Add two numbers"""
            return a + b

        result = tools.execute("add", {"a": 3, "b": 4})
        assert result == 7

        # __call__ alias
        result2 = tools("add", {"a": 10, "b": 20})
        assert result2 == 30

    def test_remove(self):
        tools = Tools()

        @tools.add
        def foo():
            pass

        @tools.add
        def bar():
            pass

        assert len(tools) == 2
        tools.remove("foo")
        assert len(tools) == 1
        assert "foo" not in tools
        assert "bar" in tools

    def test_definitions_format(self):
        tools = Tools()

        @tools.add
        def greet(name: str, age: int = 18) -> str:
            """Greet someone"""
            return f"{name} is {age}"

        defs = tools.definitions()
        assert len(defs) == 1

        d = defs[0]
        assert d["type"] == "function"
        assert d["function"]["name"] == "greet"
        assert d["function"]["description"] == "Greet someone"

        params = d["function"]["parameters"]
        assert params["type"] == "object"
        assert "name" in params["properties"]
        assert "age" in params["properties"]
        assert params["required"] == ["name"]  # age has default

    def test_execute_unknown_tool(self):
        tools = Tools()
        try:
            tools.execute("nonexistent", {})
            assert False, "应该抛出 ValueError"
        except ValueError:
            pass

    def test_tool_repr(self):
        tool = Tool(name="test", description="A test tool", handler=lambda x: x)
        assert repr(tool) == "Tool(name='test')"

    def test_tools_repr(self):
        tools = Tools()

        @tools.add
        def a():
            pass

        @tools.add
        def b():
            pass

        r = repr(tools)
        assert "a" in r
        assert "b" in r
