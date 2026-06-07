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


def _draw_input_bar(stdscr: curses.window, y: int, text: str, w: int) -> Tuple[int, int]:
    """Draw the input bar and return the (cursor_x, y) position."""
    # Clear the input area (3 lines)
    for i in range(3):
        stdscr.addstr(y + i, 0, " " * (w - 1))

    prefix = "> "
    max_input_w = w - len(prefix) - 2
    display_text = text
    cursor_x = len(prefix) + len(text)

    if len(text) > max_input_w:
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
        x = len(prefix)
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
        tool_names = agent.tools.list_tools()
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
    lines = render_markdown(text, max(width - 8, 20))
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
    curses.curs_set(1)

    input_text = ""
    message_log: List[Tuple[str, bool]] = []  # (text, is_user)
    scroll_offset = 0

    while True:
        h, w = stdscr.getmaxyx()
        status_h = 1
        input_h = 3
        chat_h = h - status_h - input_h

        if chat_h < 3:
            stdscr.addstr(0, 0, "Terminal too small! Resize.")
            stdscr.refresh()
            continue

        key = stdscr.getch()

        if key == ord("\n") or key == curses.KEY_ENTER:
            cmd = input_text.strip()

            if cmd == "":
                continue

            if cmd.startswith("//"):
                # Literal text starting with /: strip one / and send to AI
                cmd = cmd[1:]
            elif cmd.startswith("/"):
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
                            message_log.append((collected, False))
                            streaming_idx = len(message_log) - 1
                        else:
                            message_log[streaming_idx] = (collected, False)
                        _draw_chat(stdscr, message_log, scroll_offset, chat_h, w)
                        stdscr.refresh()
                    elif event["type"] == "tool_call":
                        name = event["data"]["function"]["name"]
                        message_log.append((f"[⚙ calling {name}...]", False))
                        _draw_chat(stdscr, message_log, scroll_offset, chat_h, w)
                        stdscr.refresh()
                    elif event["type"] == "tool_result":
                        name = event["data"]["name"]
                        # Replace the last "[⚙ calling...]" line with a done message
                        for i in range(len(message_log) - 1, -1, -1):
                            txt, _ = message_log[i]
                            if txt.startswith("[⚙") and name in txt:
                                message_log[i] = (f"[✅ {name} completed]", False)
                                break
                        _draw_chat(stdscr, message_log, scroll_offset, chat_h, w)
                        stdscr.refresh()
                    elif event["type"] == "error":
                        if streaming_idx is not None:
                            message_log.pop(streaming_idx)
                        message_log.append((f"Error: {event['data']}", False))

            except Exception as e:
                message_log.append((f"Error: {e}", False))

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
        cursor_x, input_y = _draw_input_bar(stdscr, h - input_h, input_text, w)
        _draw_status_bar(stdscr, agent)
        stdscr.move(input_y, cursor_x)
        stdscr.refresh()


def _total_lines(message_log: List[Tuple[str, bool]]) -> int:
    """Estimate total display lines for the log."""
    total = 0
    for text, _ in message_log:
        total += text.count("\n") + 1 + 2
    return total


def _draw_chat(
    stdscr: curses.window,
    message_log: List[Tuple[str, bool]],
    scroll_offset: int,
    chat_h: int,
    w: int,
) -> None:
    """Draw the conversation panel."""
    total_estimate = _total_lines(message_log) + chat_h
    pad = curses.newpad(max(total_estimate, chat_h + 1), w)
    pad_y = 0

    for text, is_user in message_log:
        if text == "_thinking_":
            pad.addstr(pad_y, 0, "Thinking...", curses.A_DIM)
            pad_y += 2
            continue
        pad_y = _render_and_draw(pad, pad_y, text, w, is_user)

    visible_start = max(0, pad_y - chat_h - scroll_offset)
    if visible_start > pad_y - chat_h:
        visible_start = max(0, pad_y - chat_h)

    pad.refresh(visible_start, 0, 1, 0, chat_h, w - 1)
