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
        if result.get("finish_reason") == "max_rounds":
            if self.on_error is not None:
                self.on_error(f"Reached max tool rounds ({result.get('tool_rounds', '?')})")
        elif self.on_message is not None:
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

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError) as e:
            raise ValueError(f"Invalid conversation file {path!r}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"Expected root object, got {type(data).__name__}")

        version = data.get("version", 1)
        if not isinstance(version, int) or version > 1:
            raise ValueError(f"Unsupported conversation version {version}")

        messages: List[Dict[str, Any]] = []
        if data.get("system_prompt"):
            messages.append({"role": "system", "content": data["system_prompt"]})
        messages.extend(data.get("messages", []))

        self.bot.messages = messages
        if data.get("model"):
            self.bot.model = data["model"]
        if data.get("temperature") is not None:
            self.bot.temperature = data["temperature"]

    def add_tool(self, func=None, *, name=None, description=None, parameters=None) -> Callable[..., Any]:
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
            f"tools={repr(self.tools)}, "
            f"messages={len(self.bot.messages)})"
        )
