# Agent Enhancements + Curses CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) for tracking.

**Goal:** Upgrade the Agent class with lifecycle management, event hooks, and session persistence. Build a curses-based interactive CLI (`ai-chat`) with markdown rendering and one-shot mode.

**Architecture:** The Agent class wraps AIBot + Tools and adds orchestration. The CLI is a separate consumer: `cli.py` (argparse dispatch), `cli_config.py` (config loading), `cli_markdown.py` (rich-based rendering), `cli_curses.py` (curses TUI).

**Tech Stack:** Python 3.8+, curses (stdlib), rich (optional CLI dependency), tomllib/tomli (optional CLI dependency)

---

### Task 1: Rewrite Agent — Constructor, Lifecycle, and Event Hooks

**Files:**
- Modify: `src/ai_util/agent.py` (full rewrite)

- [ ] **Step 1: Write the new Agent class with constructor, hooks, send_msg, stream_msg**

Replace the entire `src/ai_util/agent.py` with:

```python
"""
Agent - High-level AIBot + Tools wrapper with event hooks and session management.

Exports:
    Agent
"""

__all__ = [
    "Agent",
]

from typing import Any, Callable, Dict, Generator, List, Optional
from .tools import Tools
from .bot import AIBot


class Agent:
    """
    High-level wrapper combining AIBot with Tools.

    Features:
      - send_msg: non-streaming with auto tool loop
      - stream_msg: streaming with text + tool call events
      - Event hooks: on_tool_call, on_tool_result, on_error, on_message
      - Lifecycle: reset(), set_system_prompt(), history()
      - Session persistence: export_history(), import_history()
      - Tool management: add_tool(), remove_tool()
    """

    def __init__(
        self,
        bot: AIBot,
        tools: Tools,
        *,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[str, str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.bot = bot
        self.tools = tools
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result
        self.on_error = on_error
        self.on_message = on_message

    def send_msg(self, msg: str) -> Dict[str, Any]:
        """
        Send a message with auto tool loop (non-streaming).

        Fires on_message hook after the response is received.

        Returns:
            {"content": str, "finish_reason": str, "tool_rounds": int}
        """
        result = self.bot.send_msg_with_tools(msg, self.tools)
        if self.on_message is not None:
            self.on_message({
                "role": "assistant",
                "content": result.get("content", ""),
            })
        return result

    def stream_msg(self, msg: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream a message with text + tool call events.

        Fires hooks as events stream in:
          tool_call  -> on_tool_call(name, args)
          tool_result -> on_tool_result(name, result)
          error      -> on_error(msg)
          done       -> on_message({"role": "assistant", "content": ...})

        Yields the same events as AIBot.stream_output.
        """
        for event in self.bot.stream_output(
            msg, self.tools.definitions(), self.tools.execute
        ):
            if event["type"] == "tool_call" and self.on_tool_call is not None:
                self.on_tool_call(
                    event["data"]["function"]["name"],
                    event["data"]["function"]["arguments"],
                )
            elif event["type"] == "tool_result" and self.on_tool_result is not None:
                self.on_tool_result(
                    event["data"]["name"],
                    event["data"]["result"],
                )
            elif event["type"] == "error" and self.on_error is not None:
                self.on_error(event["data"])
            elif event["type"] == "done" and self.on_message is not None:
                self.on_message({
                    "role": "assistant",
                    "content": event["data"],
                })
            yield event

    def reset(self) -> None:
        """Clear conversation history (keeps system prompt)."""
        self.bot.reset()

    def set_system_prompt(self, prompt: str) -> None:
        """Replace or add the system prompt message."""
        for i, msg in enumerate(self.bot.messages):
            if msg.get("role") == "system":
                self.bot.messages[i] = {"role": "system", "content": prompt}
                return
        self.bot.messages.insert(0, {"role": "system", "content": prompt})

    def history(self) -> List[Dict[str, Any]]:
        """Get a read-only copy of the conversation history."""
        return list(self.bot.messages)

    def export_history(self, path: str) -> None:
        """Save the conversation to a JSON file."""
        import json

        system_prompt: Optional[str] = None
        for msg in self.bot.messages:
            if msg.get("role") == "system":
                system_prompt = msg["content"]
                break

        data = {
            "version": 1,
            "system_prompt": system_prompt,
            "model": self.bot.model,
            "temperature": self.bot.temperature,
            "messages": [m for m in self.bot.messages if m.get("role") != "system"],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_history(self, path: str) -> None:
        """Load a conversation from a JSON file."""
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages: List[Dict[str, Any]] = []
        if data.get("system_prompt"):
            messages.append({"role": "system", "content": data["system_prompt"]})
        messages.extend(data.get("messages", []))

        self.bot.messages = messages
        if data.get("model"):
            self.bot.model = data["model"]
        if data.get("temperature") is not None:
            self.bot.temperature = data["temperature"]

    def add_tool(self, func=None, *, name=None, description=None, parameters=None):
        """Register a tool. Works as a decorator or direct call."""
        return self.tools.add(
            func, name=name, description=description, parameters=parameters
        )

    def remove_tool(self, name: str) -> None:
        """Unregister a tool by name."""
        self.tools.remove(name)

    def __repr__(self) -> str:
        return (
            f"Agent(bot={self.bot.model!r}, "
            f"tools={list(self.tools._tools.keys())}, "
            f"messages={len(self.bot.messages)})"
        )
```

- [ ] **Step 2: Verify it compiles**

```bash
python -m py_compile src/ai_util/agent.py
```
Expected: no output (exit code 0).

---

### Task 2: Write Agent Unit Tests

**Files:**
- Create: `tests/test_agent.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_agent.py`:

```python
"""Tests for the Agent class (lifecycle, hooks, persistence, tool management)."""

import json
import os
import tempfile
from unittest.mock import Mock, patch
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

    def test_on_error_hook_fires(self, monkeypatch):
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

    def test_import_validates_version(self):
        agent = _make_agent()
        data = {"version": 1, "messages": [{"role": "user", "content": "Hi"}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            agent.import_history(tmp_path)
            assert len(agent.bot.messages) == 1
        finally:
            os.unlink(tmp_path)


class TestAgentToolManagement:
    def test_add_tool_decorator(self):
        agent = _make_agent()
        @agent.add_tool
        def my_tool(x: int) -> str:
            """Test tool"""
            return str(x)
        assert "my_tool" in agent.tools
        assert agent.tools.execute("my_tool", {"x": 42}) == "42"

    def test_remove_tool(self):
        agent = _make_agent()
        @agent.add_tool
        def my_tool(x: int) -> str:
            return str(x)
        assert "my_tool" in agent.tools
        agent.remove_tool("my_tool")
        assert "my_tool" not in agent.tools
```

- [ ] **Step 2: Run the tests**

```bash
pip install -e . -q
pytest tests/test_agent.py -v
```
Expected: all tests pass.

---

### Task 3: CLI Config Module

**Files:**
- Create: `src/ai_util/cli_config.py`

- [ ] **Step 1: Write cli_config.py**

```python
"""
CLI Config — load settings from config.toml, env vars, and CLI args.

Resolution order (last wins): config file < env var < CLI argument.

Exports:
    DEFAULT_CONFIG_PATH, load_config, merge_with_cli_args
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Python 3.8–3.10


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "load_config",
    "merge_with_cli_args",
]

DEFAULT_CONFIG_PATH: Path = Path.home() / ".config" / "ai-util" / "config.toml"

# Schema of known config keys with their env-var overrides
_ENV_MAP: Dict[str, str] = {
    "api_key": "OPENAI_API_KEY",
    "base_url": "OPENAI_BASE_URL",
}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load config from a TOML file, then overlay environment variables.

    Args:
        config_path: Path to config file. Defaults to ~/.config/ai-util/config.toml.

    Returns:
        Dict with keys: api_key, base_url, model, temperature, system_prompt, etc.
    """
    config: Dict[str, Any] = {}

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, "rb") as f:
            config = tomllib.load(f)

    # Environment variables override config file
    for key, env_var in _ENV_MAP.items():
        if env_var in os.environ:
            config[key] = os.environ[env_var]

    return config


def merge_with_cli_args(config: Dict[str, Any], args: Any) -> Dict[str, Any]:
    """
    Override config dict with non-None CLI argparse values.

    Args:
        config: Dict from load_config().
        args: Namespace from argparse.parse_args().

    Returns:
        Updated config dict (modified in place for convenience).
    """
    for attr in ("api_key", "base_url", "model", "temperature", "system_prompt",
                 "prompt", "stream"):
        value = getattr(args, attr, None)
        if value is not None:
            config[attr] = value
    return config
```

- [ ] **Step 2: Verify it compiles**

```bash
python -m py_compile src/ai_util/cli_config.py
```
Expected: no output (exit code 0).

---

### Task 4: CLI Markdown Renderer

**Files:**
- Create: `src/ai_util/cli_markdown.py`

- [ ] **Step 1: Write cli_markdown.py**

```python
"""
CLI Markdown — render markdown to curses-styled lines using rich.

Exports:
    render_markdown, RICH_TO_CURSES_COLORS
"""

from typing import Any, Dict, List, Optional, Tuple
from rich.console import Console
from rich.markdown import Markdown
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from io import StringIO
import curses


__all__ = [
    "render_markdown",
    "init_color_pairs",
    "RICH_TO_CURSES_COLORS",
]

# Map rich color names (8-color palette) to curses color indices
RICH_TO_CURSES_COLORS: Dict[str, int] = {
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "blue": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
    "black": curses.COLOR_BLACK,
}

# Cache for color pairs: (fg, bg) -> pair_number
_color_pair_cache: Dict[Tuple[int, int], int] = {}
_next_pair = 1


def _get_color_pair(fg: int, bg: int = -1) -> int:
    """Get (or create) a curses color pair number for given foreground/background."""
    global _next_pair
    bg = bg if bg >= 0 else curses.COLOR_BLACK
    key = (fg, bg)
    if key not in _color_pair_cache:
        if _next_pair > 255:
            _next_pair = 1  # wrap around, reuse pairs
        curses.init_pair(_next_pair, fg, bg)
        _color_pair_cache[key] = _next_pair
        _next_pair += 1
    return curses.color_pair(_color_pair_cache[key])


def init_color_pairs() -> None:
    """Pre-initialise commonly used colour pairs for markdown rendering.

    Call this once after curses.initscr() / curses.start_color().
    """
    global _color_pair_cache, _next_pair
    _color_pair_cache.clear()
    _next_pair = 1

    # Pre-create pairs for the ANSI palette on default background
    for color_num in range(8):
        _get_color_pair(color_num)


def _rich_color_to_curses(color_name: Optional[str]) -> int:
    """Convert a rich colour name to a curses colour number."""
    if color_name is None:
        return curses.COLOR_WHITE  # default foreground
    return RICH_TO_CURSES_COLORS.get(color_name, curses.COLOR_WHITE)


def _style_to_curses_attr(style: Style) -> int:
    """Convert a rich Style to a single curses attribute + colour bitmask."""
    attr = 0

    fg_color = _rich_color_to_curses(style.color.name if style.color else None)
    bg_color = curses.COLOR_BLACK
    if style.bgcolor is not None:
        bg_color = _rich_color_to_curses(style.bgcolor.name)

    attr |= _get_color_pair(fg_color, bg_color)

    if style.bold:
        attr |= curses.A_BOLD
    if style.italic:
        attr |= curses.A_ITALIC
    if style.underline:
        attr |= curses.A_UNDERLINE
    if style.strike:
        attr |= curses.A_STANDOUT

    return attr


def render_markdown(text: str, width: int) -> List[List[Tuple[str, int]]]:
    """
    Render markdown to a list of lines.

    Each line is a list of (text_segment, curses_attribute) tuples
    that should be concatenated for display.

    Args:
        text: Raw markdown string.
        width: Target line width for wrapping.

    Returns:
        Lines ready for curses.addstr() usage.
    """
    md = Markdown(text, code_theme="monokai")
    console = Console(
        width=width,
        force_terminal=True,
        color_system="standard",
        legacy_windows=False,
    )

    rendered_segments = console.render(md)
    segments = list(Segment.split_lines(rendered_segments))

    lines: List[List[Tuple[str, int]]] = []
    for seg_line in segments:
        line: List[Tuple[str, int]] = []
        for segment in seg_line:
            if segment.text is None:
                continue
            attr = _style_to_curses_attr(segment.style or Style())
            line.append((segment.text, attr))
        lines.append(line)

    return lines


def render_plain(text: str, width: int) -> str:
    """Render markdown to plain text (no styling), for use in one-shot mode."""
    md = Markdown(text, code_theme="monokai")
    console = Console(width=width, force_terminal=False, color_system=None)
    with console.capture() as capture:
        console.print(md)
    return capture.get()
```

- [ ] **Step 2: Verify it compiles**

```bash
python -m py_compile src/ai_util/cli_markdown.py
```
Expected: no output (exit code 0).

---

### Task 5: Curses TUI — Core Chat Application

**Files:**
- Create: `src/ai_util/cli_curses.py`

- [ ] **Step 1: Write the curses TUI**

```python
"""
CLI Curses — interactive curses-based chat TUI.

Exports:
    run_curses_app
"""

import curses
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from .agent import Agent
from .cli_markdown import render_markdown, init_color_pairs


__all__ = [
    "run_curses_app",
]


# Command registry
_COMMANDS: Dict[str, str] = {
    "help": "Show this help message",
    "reset": "Clear conversation history",
    "clear": "Clear the screen",
    "tools": "List registered tools",
    "model": "Switch model: /model <name>",
    "sysprompt": "Change system prompt: /sysprompt <text>",
    "save": "Save session: /save <path>",
    "load": "Load session: /load <path>",
    "export": "Export history: /export <path>",
}


def _draw_status_bar(stdscr: curses.window, agent: Agent) -> None:
    """Draw the top status bar with model and tool info."""
    h, w = stdscr.getmaxyx()
    model = agent.bot.model
    tool_count = len(agent.tools)
    status = f" Model: {model}  |  Tools: {tool_count}  |  CTRL+Q quit  |  /help"
    stdscr.addstr(0, 0, status[:w - 1], curses.A_REVERSE)


def _draw_input_bar(stdscr: curses.window, y: int, text: str) -> int:
    """Draw the input bar and return the cursor x position."""
    h, w = stdscr.getmaxyx()
    # Clear the full input area (3 lines minimum)
    for i in range(3):
        stdscr.addstr(y + i, 0, " " * (w - 1))

    prefix = "> "
    max_input_w = w - len(prefix) - 2
    display_text = text
    cursor_x = len(prefix) + len(text)

    if len(text) > max_input_w:
        # Scroll input horizontally
        offset = len(text) - max_input_w
        display_text = text[offset:]
        cursor_x = len(prefix) + max_input_w

    stdscr.addstr(y, 0, prefix + display_text)
    return cursor_x, y


def _draw_message(
    pad: curses.window,
    pad_y: int,
    lines: List[List[Tuple[str, int]]],
    width: int,
    is_user: bool,
) -> int:
    """Draw a message (user or assistant) into the pad. Returns new pad_y."""
    prefix = "You:  " if is_user else "Bot:  "
    pad.addstr(pad_y, 0, prefix, curses.A_BOLD)

    for line in lines:
        if pad_y >= 10000:
            break
        x = 6  # indent after prefix
        for seg_text, attr in line:
            if x >= width:
                break
            available = width - x
            if len(seg_text) > available:
                pad.addstr(pad_y, x, seg_text[:available], attr)
                x = width
            else:
                pad.addstr(pad_y, x, seg_text, attr)
                x += len(seg_text)
        pad_y += 1

    pad_y += 1  # blank line between messages
    return pad_y


def _handle_command(cmd: str, agent: Agent) -> Optional[str]:
    """Handle a /command. Returns a response message or None."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        lines = ["Available commands:"]
        for name, desc in _COMMANDS.items():
            lines.append(f"  /{name:<12} {desc}")
        return "\n".join(lines)

    elif command == "/reset":
        agent.reset()
        return "Conversation reset."

    elif command == "/clear":
        return "__clear__"

    elif command == "/tools":
        tool_names = list(agent.tools._tools.keys())
        if tool_names:
            return "Registered tools:\n  " + "\n  ".join(tool_names)
        return "No tools registered."

    elif command == "/model":
        if arg:
            agent.bot.model = arg
            return f"Model switched to {arg}."
        return f"Current model: {agent.bot.model}"

    elif command == "/sysprompt":
        if arg:
            agent.set_system_prompt(arg)
            return "System prompt updated."
        return "Usage: /sysprompt <text>"

    elif command == "/save":
        if arg:
            agent.export_history(arg)
            return f"Session saved to {arg}."
        return "Usage: /save <path>"

    elif command == "/load":
        if arg:
            agent.import_history(arg)
            return f"Session loaded from {arg}."
        return "Usage: /load <path>"

    elif command == "/export":
        if arg:
            agent.export_history(arg)
            return f"History exported to {arg}."
        return "Usage: /export <path>"

    return f"Unknown command: {command}. Type /help for available commands."


def _render_and_draw(
    pad: curses.window,
    pad_y: int,
    text: str,
    width: int,
    is_user: bool,
) -> int:
    """Render markdown and draw to pad. Returns new pad_y."""
    lines = render_markdown(text, width - 8)
    return _draw_message(pad, pad_y, lines, width, is_user)


def run_curses_app(agent: Agent) -> None:
    """
    Run the curses interactive chat application.

    Args:
        agent: A configured Agent instance (bot + tools ready).
    """
    stdscr = curses.initscr()
    curses.start_color()
    curses.use_default_colors()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    # Enable colour if supported
    if curses.has_colors():
        curses.start_color()
        init_color_pairs()

    try:
        _run(stdscr, agent)
    finally:
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()


def _run(stdscr: curses.window, agent: Agent) -> None:
    """Internal curses event loop."""
    curses.curs_set(1)  # show cursor

    input_text = ""
    message_log: List[Tuple[str, bool]] = []  # (text, is_user)

    # Scroll offset for the pad
    scroll_offset = 0

    while True:
        h, w = stdscr.getmaxyx()
        status_h = 1
        input_h = 3
        chat_h = h - status_h - input_h

        if chat_h < 1:
            stdscr.addstr(0, 0, "Terminal too small! Resize.")
            stdscr.refresh()
            continue

        # Read key
        key = stdscr.getch()

        if key == ord("\n") or key == curses.KEY_ENTER:
            cmd = input_text.strip()

            if cmd == "":
                continue

            if cmd.startswith("/"):
                # Slash command
                result = _handle_command(cmd, agent)
                if result == "__clear__":
                    message_log.clear()
                    scroll_offset = 0
                elif result is not None:
                    message_log.append((f"/command: {cmd}", True))
                    message_log.append((result, False))
                input_text = ""
                continue

            # Send to AI
            message_log.append((cmd, True))
            input_text = ""

            try:
                # Show "Thinking..." temporarily
                message_log.append(("_thinking_", False))
                _draw_chat(stdscr, message_log, scroll_offset, chat_h, w)
                stdscr.refresh()
                message_log.pop()

                # Stream the response — update message in-place on each chunk
                collected = ""
                streaming_idx: Optional[int] = None

                for event in agent.stream_msg(cmd):
                    if event["type"] == "content":
                        collected += event["data"]
                        if streaming_idx is None:
                            # First chunk — append a new assistant message
                            message_log.append((collected, False))
                            streaming_idx = len(message_log) - 1
                        else:
                            # Subsequent chunks — replace in-place
                            message_log[streaming_idx] = (collected, False)
                        _draw_chat(stdscr, message_log, scroll_offset, chat_h, w)
                        stdscr.refresh()
                    elif event["type"] == "error":
                        if streaming_idx is not None:
                            message_log.pop(streaming_idx)
                        message_log.append((f"Error: {event['data']}", False))

            except Exception as e:
                message_log.append((f"Error: {e}", False))

            # Auto-scroll to bottom
            scroll_offset = 0

        elif key == curses.KEY_BACKSPACE or key == 127:
            input_text = input_text[:-1]

        elif key == curses.KEY_PP:  # Page Up
            scroll_offset = min(scroll_offset + chat_h // 2,
                                _total_lines(message_log))
        elif key == curses.KEY_NP:  # Page Down
            scroll_offset = max(scroll_offset - chat_h // 2, 0)

        elif key == ord("\x15"):  # CTRL+U — clear input
            input_text = ""

        elif key == 17:  # CTRL+Q — quit
            break

        elif 32 <= key <= 126:
            input_text += chr(key)

        # Draw
        _draw_chat(stdscr, message_log, scroll_offset, chat_h, w)
        cursor_x, input_y = _draw_input_bar(stdscr, h - input_h, input_text)
        _draw_status_bar(stdscr, agent)
        stdscr.move(input_y, cursor_x)
        stdscr.refresh()


def _total_lines(message_log: List[Tuple[str, bool]]) -> int:
    """Estimate total display lines for the log."""
    total = 0
    for text, _ in message_log:
        total += text.count("\n") + 1 + 2  # +2 for prefix/separator
    return total


def _draw_chat(
    stdscr: curses.window,
    message_log: List[Tuple[str, bool]],
    scroll_offset: int,
    chat_h: int,
    w: int,
) -> None:
    """Draw the conversation panel."""
    # Create a pad for scrolling
    total_estimate = _total_lines(message_log) + chat_h
    pad = curses.newpad(max(total_estimate, chat_h + 1), w)
    pad_y = 0

    for text, is_user in message_log:
        if text == "_thinking_":
            pad.addstr(pad_y, 0, "Thinking...", curses.A_DIM)
            pad_y += 2
            continue
        pad_y = _render_and_draw(pad, pad_y, text, w, is_user)

    # Ensure we don't scroll past the bottom
    visible_start = max(0, pad_y - chat_h - scroll_offset)
    if visible_start > pad_y - chat_h:
        visible_start = max(0, pad_y - chat_h)

    pad.refresh(visible_start, 0, 1, 0, chat_h, w - 1)
```

- [ ] **Step 2: Verify it compiles**

```bash
python -m py_compile src/ai_util/cli_curses.py
```
Expected: no output (exit code 0).

---

### Task 6: CLI Entry Point (argparse + dispatch)

**Files:**
- Create: `src/ai_util/cli.py`

- [ ] **Step 1: Write the CLI entry point**

```python
"""
CLI Entry Point — argparse dispatch for interactive and one-shot modes.

Usage:
    ai-chat                          # Interactive curses chat
    ai-chat --prompt "Hello"         # One-shot mode
    ai-chat --prompt "Hello" --stream  # One-shot with streaming
    python -m ai_util.cli            # Same as ai-chat

Exports:
    main (console_scripts entry point)
"""

import argparse
import sys
from typing import Any, Dict, List, Optional

from .bot import AIBot
from .tools import Tools
from .agent import Agent
from .cli_config import load_config, merge_with_cli_args
from .cli_curses import run_curses_app


__all__ = [
    "main",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-chat",
        description="AI Chat CLI — interactive chat with AI models",
    )
    parser.add_argument("--api-key", help="OpenAI-compatible API key")
    parser.add_argument("--base-url", help="Custom API base URL")
    parser.add_argument("--model", help="Model name (default: gpt-4o)")
    parser.add_argument("--temperature", type=float, help="Sampling temperature (0–2)")
    parser.add_argument("--system-prompt", help="System prompt for the AI")
    parser.add_argument("--prompt", help="One-shot prompt mode (non-interactive)")
    parser.add_argument("--stream", action="store_true", default=None,
                        help="Stream output in one-shot mode")
    parser.add_argument("--no-stream", action="store_true", default=None,
                        help="Non-streaming output in one-shot mode")
    parser.add_argument("--config", help="Path to config file")
    return parser


def _create_agent(config: Dict[str, Any]) -> Agent:
    """Create an Agent from a config dict."""
    bot = AIBot(
        api_key=config.get("api_key"),
        base_url=config.get("base_url"),
        model=config.get("model", "gpt-4o"),
        system_prompt=config.get("system_prompt"),
        temperature=config.get("temperature", 0.7),
    )
    tools = Tools()
    return Agent(bot=bot, tools=tools)


def _run_one_shot(agent: Agent, prompt: str, use_stream: bool) -> None:
    """Run in one-shot mode: print response and exit."""
    if use_stream:
        for event in agent.stream_msg(prompt):
            if event["type"] == "content":
                print(event["data"], end="", flush=True)
            elif event["type"] == "done":
                print()
            elif event["type"] == "error":
                print(f"\nError: {event['data']}", file=sys.stderr)
    else:
        result = agent.send_msg(prompt)
        content = result.get("content", "") or ""
        print(content)


def _resolve_stream_flag(args: Any) -> bool:
    """Determine whether to use streaming in one-shot mode."""
    if args.stream:
        return True
    if args.no_stream:
        return False
    # Default: stream if stdout is a terminal
    return sys.stdout.isatty()


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for ai-chat."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Load config
    config = load_config(args.config)
    merge_with_cli_args(config, args)

    # Create agent
    agent = _create_agent(config)

    if config.get("prompt"):
        # One-shot mode
        use_stream = _resolve_stream_flag(args)
        _run_one_shot(agent, config["prompt"], use_stream)
    else:
        # Interactive curses mode
        run_curses_app(agent)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it compiles**

```bash
python -m py_compile src/ai_util/cli.py
```
Expected: no output (exit code 0).

---

### Task 7: Update pyproject.toml with Entry Point + Optional Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add entry point and optional deps**

Insert after the `dependencies` list in `pyproject.toml`:

```toml
[project.scripts]
ai-chat = "ai_util.cli:main"

[project.optional-dependencies]
cli = [
    "rich>=13.0.0",
    "tomli>=1.1.0; python_version < '3.11'",
]
```

The edit replaces the blank line after `dependencies` with the new sections. The exact old_string/new_string:

old_string:
```
dependencies = [
  "openai>=1.0.0",
  "requests>=2.26.0",
]

[project.urls]
```

new_string:
```
dependencies = [
  "openai>=1.0.0",
  "requests>=2.26.0",
]

[project.scripts]
ai-chat = "ai_util.cli:main"

[project.optional-dependencies]
cli = [
    "rich>=13.0.0",
    "tomli>=1.1.0; python_version < '3.11'",
]

[project.urls]
```

- [ ] **Step 2: Install the CLI extras and verify the entry point works**

```bash
pip install -e ".[cli]" -q
ai-chat --help
```
Expected: help text with all flags.

---

### Task 8: Manual Integration Smoke Test

**Files:**
- No file changes — manual verification

- [ ] **Step 1: Run a one-shot test (if API key is configured)**

```bash
OPENAI_API_KEY="sk-xxx" ai-chat --prompt "Say hello in one word" --no-stream
```
Expected: prints a response and exits.

- [ ] **Step 2: Run interactive mode (if API key is configured)**

```bash
OPENAI_API_KEY="sk-xxx" ai-chat
```
Expected: curses interface loads, typing a message sends it, CTRL+Q exits.

---

## File Summary

### Created (5 files)
| File | Lines (est.) | Purpose |
|------|-------------|---------|
| `tests/test_agent.py` | ~170 | Unit tests for Agent |
| `src/ai_util/cli_config.py` | ~70 | Config file + env var loading |
| `src/ai_util/cli_markdown.py` | ~150 | Markdown → curses rendering via rich |
| `src/ai_util/cli_curses.py` | ~280 | Curses TUI chat application |
| `src/ai_util/cli.py` | ~100 | Argparse dispatch + entry point |

### Modified (2 files)
| File | Change |
|------|--------|
| `src/ai_util/agent.py` | Full rewrite: hooks, lifecycle, persistence, tool mgmt |
| `pyproject.toml` | Add entry point + `[cli]` optional dependencies |
