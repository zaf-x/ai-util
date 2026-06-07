# Agent Enhancements + Curses CLI — Design Spec

## Overview

Upgrade the `Agent` class with full conversation lifecycle management, event hooks, and session persistence. Build a curses-based interactive CLI (`ai-chat`) with markdown rendering and one-shot mode.

## 1. Agent Enhancements

### 1.1 New API

```python
class Agent:
    def __init__(
        self,
        bot: AIBot,
        tools: Tools,
        on_tool_call: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_message: Callable[[dict], None] | None = None,
    )
```

### 1.2 Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `send_msg(msg)` | `dict` | Send message with auto tool loop |
| `stream_msg(msg)` | `Generator[dict]` | Stream with text + tool call events |
| `reset()` | `None` | Clear history (keep system prompt) |
| `set_system_prompt(prompt)` | `None` | Replace system prompt in-place |
| `history()` | `list[dict]` | Read-only conversation copy |
| `export_history(path)` | `None` | Save to JSON file |
| `import_history(path)` | `None` | Load from JSON file |
| `add_tool(func, ...)` | `Callable` | Register a tool (supports decorator) |
| `remove_tool(name)` | `None` | Unregister a tool |

### 1.3 Event Hooks

All optional callables. Fire during `send_msg` and `stream_msg`:

- **`on_message(msg_dict)`** — after each assistant message appended to history
- **`on_tool_call(name, args)`** — before tool execution
- **`on_tool_result(name, result)`** — after tool execution with result string
- **`on_error(error_str)`** — on unrecoverable errors

### 1.4 Session Persistence Format

JSON file schema (`.json` extension):

```json
{
    "version": 1,
    "system_prompt": "...",
    "model": "gpt-4o",
    "temperature": 0.7,
    "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "...", "tool_calls": [...]},
        {"role": "tool", "tool_call_id": "...", "content": "..."}
    ]
}
```

## 2. CLI Architecture

### 2.1 Entry Points

- `ai-chat` — interactive curses chat (registered in `pyproject.toml`)
- `python -m ai_util.cli` — same as above
- `ai-chat --prompt "msg"` — one-shot mode, print response to stdout
- `ai-chat --prompt "msg" --stream` — one-shot with streaming

### 2.2 Config Resolution

Precedence: CLI arg > environment variable > config file.

Config file: `~/.config/ai-util/config.toml`

```toml
api_key = "sk-xxx"
base_url = "https://api.openai.com/v1"
model = "gpt-4o"
temperature = 0.7
system_prompt = "You are a helpful assistant."
```

CLI flags: `--api-key`, `--base-url`, `--model`, `--temperature`, `--system-prompt`, `--prompt`, `--stream`, `--no-stream`.

Env vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`.

### 2.3 Curses Layout

```
┌──────────────────────────────────────────────────┐
│ Status Bar: Model | Tools: N | CTRL+Q quit       │  1 line
├──────────────────────────────────────────────────┤
│                                                   │
│ Conversation Panel (scrollable)                   │
│   User messages aligned right                     │
│   Assistant messages aligned left                 │
│   Tool calls shown inline (dim style)             │
│   Markdown rendered in full                       │
│   Long lines wrapped                              │
│                                                   │
├──────────────────────────────────────────────────┤
│ Input Bar: > _                                    │  3 lines min
└──────────────────────────────────────────────────┘
```

Window resizing via `SIGWINCH` triggers full re-layout.

### 2.4 Chat Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/reset` | Clear conversation history |
| `/clear` | Clear screen |
| `/tools` | List registered tools |
| `/model <name>` | Switch model |
| `/sysprompt <text>` | Change system prompt |
| `/save <path>` | Save session to file |
| `/load <path>` | Load session from file |
| `/export <path>` | Export history to JSON |
| `//text` | Send literal text starting with `/` |

### 2.5 Streaming Display Flow

1. User message appended to panel immediately
2. Assistant bubble starts empty, grows as `content` events arrive (character-by-character typing effect)
3. `tool_call` → dimmed `[⚙ calling get_weather...]` line appears
4. `tool_result` → line updates to `[✅ get_weather returned]`
5. `reasoning` → dimmed italic text (if model supports it)
6. `done` → response complete
7. `error` → red text

### 2.6 One-shot Mode

```
ai-chat --prompt "hello" --no-stream
→ plain text response to stdout

ai-chat --prompt "hello" --stream
→ streaming text to stdout (plain, no curses)
```

### 2.7 Error Handling

- API errors → red in curses, stderr in one-shot
- Network timeout → `[Connection timeout]` message
- Invalid config → warning, fallback to env vars
- Terminal too small → minimal layout warning

## 3. File Organization

### New files

```
src/ai_util/
├── cli.py              # argparse + dispatch (interactive vs one-shot)
├── cli_curses.py       # curses TUI: layout, input, streaming display
├── cli_markdown.py     # Markdown → curses renderer (rich wrapper)
└── cli_config.py       # Config file loading (tomllib/stdlib)
```

### Modified files

```
src/ai_util/
├── agent.py             # Rewrite with hooks, persistence, lifecycle
├── __init__.py          # No change needed (Agent already exported)

pyproject.toml           # Add entry point + optional deps
```

## 4. Dependencies

### Core (unchanged)

- `openai>=1.0.0`
- `requests>=2.26.0`

### CLI optional

```toml
[project.optional-dependencies]
cli = [
    "rich>=13.0.0",
]
```

## 5. Dependency Graph

```
ai-chat ➔ cli.py ➔ cli_config.py  (config.toml)
                 ➔ cli_curses.py   (curses UI)
                      ➔ cli_markdown.py  (rich for markdown)
                 ➔ Agent           (enhanced)
                      ➔ AIBot + Tools
```

## 6. Testing

- Unit tests for Agent: `test_agent.py`
  - `export_history` / `import_history` round-trip
  - Event hooks fire correctly
  - `add_tool` / `remove_tool`
  - `set_system_prompt`
  - `reset()` preserves system prompt

- Manual test for CLI: not unit-testable due to curses

## 7. Out of Scope

- Multi-agent coordination
- Plugin system for tools
- Web UI
- Image generation/display in CLI
- Sound/notifications
