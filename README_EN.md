# ai-util

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ai-util** is a practical and elegant AI wrapper toolkit designed with an OOP style, built on top of the OpenAI SDK. It enables you to interact with AI models using less code and cleaner interfaces.

### Core Features

- **🎯 Concise OOP Design** — `AIBot` main class + `Tools` toolkit + `Agent` high-level wrapper, ready to use out of the box
- **📡 Streaming + Tool Calling Simultaneously** — Receive text deltas and tool call deltas in the same stream; automatically continues the conversation after tool execution
- **🔧 Automatic Tool Registration** — Register tool functions via decorators, with parameter schemas automatically inferred from type annotations
- **🔄 Automatic Tool Loop** — `send_msg_with_tools` handles the complete loop of tool calling → execution → conversation continuation in a single line
- **🤖 Agent High-Level Wrapper** — The `Agent` class binds `AIBot` with `Tools`, simplifying invocations
- **🔒 Built-in Sandbox Tools** — `Sandbox` provides a secure set of file I/O, system command, and network request tools, giving AI environment interaction capabilities with one click
- **📝 Conversation History Management** — Automatically maintains message lists, supports reset and export
- **🔗 Compatible with Any OpenAI-Style API** — Supports DeepSeek, Tongyi Qianwen, GLM, and other compatible APIs

---

## Installation

```bash
pip install git+https://github.com/BaoShuWen/ai-util.git
```

Requires Python 3.8+ and `openai>=1.0.0`.

## Quick Start

### Basic Conversation

```python
from ai_util import AIBot

bot = AIBot(
    api_key="sk-xxx",                # Or set the OPENAI_API_KEY environment variable
    model="gpt-4o",
    system_prompt="You are a helpful assistant.",
)

# Non-streaming
resp = bot.send_msg("Hello!")
print(resp["content"])

# Streaming
for chunk in bot.stream_output("Tell me a story"):
    if chunk["type"] == "content":
        print(chunk["data"], end="", flush=True)
```

### Using Tools

```python
from ai_util import AIBot, Tools

tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """Get the weather for a specified city"""
    return f"{city}: Sunny, 25°C, Light breeze"

bot = AIBot(model="gpt-4o")
result = bot.send_msg_with_tools("How's the weather in Beijing?", tools)
print(result["content"])
```

### Using Agent (High-Level Wrapper)

```python
from ai_util import AIBot, Tools, Agent

tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """Get the weather for a specified city"""
    return f"{city}: Sunny, 25°C, Light breeze"

bot = AIBot(
    api_key="sk-xxx",
    model="gpt-4o",
    system_prompt="You are a helpful assistant.",
)

agent = Agent(bot=bot, tools=tools)

# Non-streaming — automatic tool execution
result = agent.send_msg("How's the weather in Beijing?")
print(result["content"])

# Streaming — text + tool calls handled simultaneously
for event in agent.stream_msg("How's the weather in Shanghai?"):
    if event["type"] == "content":
        print(event["data"], end="", flush=True)
    elif event["type"] == "tool_call":
        print(f"\n[Calling {event['data']['function']['name']}]")
    elif event["type"] == "tool_result":
        print(f"\n[Tool returned: {event['data']['result']}]")
```

### Using Sandbox Tools (Giving AI Environment Interaction Capabilities)

```python
from ai_util import AIBot, Tools, Agent, Sandbox

# Create a sandbox restricted to /home/user/workspace
tools = Tools()
sandbox = Sandbox("/home/user/workspace")
sandbox.register_tools(tools)

bot = AIBot(api_key="sk-xxx", model="gpt-4o")
agent = Agent(bot=bot, tools=tools)

# AI can now read, edit files, send HTTP requests, and run system commands
result = agent.send_msg("Please read the contents of main.py and tell me what it does")
print(result["content"])
```

---

## Streaming Output in Detail

This is the core feature of `ai-util`: **handling text output and tool calls in a single stream**, automatically continuing the conversation after tool execution, without manually managing loops.

### How It Works

Internal flow of `stream_output` (and `Agent.stream_msg`):

```
User Message
    │
    ▼
┌──────────────────┐
│  Call AI API      │  ← Streaming mode
│  (stream=True)    │
└────────┬─────────┘
         │
    ┌────┴────┐
    │ Text    │  → yield {"type": "content", "data": "..."}
    │ Deltas  │
    └────┬────┘
         │
    ┌────┴────┐
    │ Tool    │  → yield {"type": "tool_call_delta", ...}
    │ Call    │     yield {"type": "tool_call", ...}
    │ Deltas  │
    └────┬────┘
         │
    ┌────┴────┐
    │ Execute │  → yield {"type": "tool_result", ...}
    │ Tools   │     Automatically appended to conversation history
    │ (Local) │
    └────┬────┘
         │
    ┌────┴────┐
    │ Continue│  ← Recursive: AI may call tools again
    │ API Call│     or return final text
    └────┬────┘
         │
    ┌────┴────┐
    │ Stream  │  → yield {"type": "done", "data": "..."}
    │ Ends    │
    └─────────┘
```

**Key Behaviors:**
- Tool calls are executed locally (not via API), and results are immediately sent back to the conversation
- Multi-round tool calls are handled automatically via recursion until the model no longer requests tools
- The `max_tool_rounds` parameter prevents infinite loops (default: 10 rounds)

### Event Types in Detail

Each event is a `dict` containing a `type` identifier and `data` payload:

#### content — Text Delta

```python
{
    "type": "content",
    "data": "Beijing"           # Text fragment pushed incrementally
}
```

Model-generated text is pushed incrementally in chunks. The caller should concatenate all `content` events to obtain the full text.

#### reasoning — Reasoning Process (supported by some models)

```python
{
    "type": "reasoning",
    "data": "Let me check the weather in Beijing..."   # Model's reasoning process / chain of thought
}
```

Some models (e.g., DeepSeek-R1) output a reasoning process before the final answer. This event interleaves with `content` events.

#### tool_call_delta — Tool Call Delta

```python
{
    "type": "tool_call_delta",
    "data": {
        "index": 0,          # Tool call index (multiple tools may be called in the same round)
        "id": "call_abc",    # Call ID; non-empty on first appearance, may be empty in subsequent deltas
        "name": "get_",      # Tool name delta (may be pushed in multiple chunks)
        "arguments": '{"ci'  # Parameter JSON delta (may be pushed in multiple chunks)
    }
}
```

When the model decides to call a tool, the tool name and arguments are pushed incrementally. Typically used to display real-time progress (e.g., typewriter-style `[Calling get_weather...]`).

**Note:** `name` and `arguments` are incrementally concatenated and may be incomplete when used directly. For complete data, use the `tool_call` event.

#### tool_call — Complete Tool Call

```python
{
    "type": "tool_call",
    "data": {
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": "{\"city\": \"Beijing\"}"
        }
    }
}
```

Triggered when the stream ends and the tool call has been fully collected. At this point, `arguments` is a complete JSON string that can be parsed directly.

#### tool_result — Tool Execution Result

```python
{
    "type": "tool_result",
    "data": {
        "name": "get_weather",
        "result": "Beijing: Sunny, 22°C, Humidity 30%"   # Tool function return value (stringified)
    }
}
```

Triggered after the tool is executed locally. `result` is the tool function's return value serialized via `json.dumps`, or a plain string.

#### done — Stream End

```python
{
    "type": "done",
    "data": "The weather in Beijing is..."   # Final concatenation of all text deltas in this round
}
```

The streaming output is completely finished; no more events will follow. `data` is the complete final response text.

#### error — Error

```python
{
    "type": "error",
    "data": "Tool call exceeded maximum rounds (10)"
}
```

Triggered when an unrecoverable error occurs. After this, the stream ends and no further events are produced.

### Event Type Quick Reference

| type | data type | data content | trigger timing |
|------|-----------|--------------|----------------|
| `"content"` | `str` | Text fragment | Pushed chunk by chunk as the model generates text |
| `"reasoning"` | `str` | Reasoning process text | Pushed as the model thinks (supported by some models) |
| `"tool_call_delta"` | `dict` | `{index, id, name, arguments}` | Streaming delta of a tool call |
| `"tool_call"` | `dict` | `{id, type, function: {name, arguments}}` | When complete tool call data is ready |
| `"tool_result"` | `dict` | `{name, result}` | After tool execution completes |
| `"done"` | `str` | Complete response text | When the stream fully ends |
| `"error"` | `str` | Error description | When an unrecoverable error occurs |

### Complete Event Stream Example

Assume the user asks "How's the weather in Beijing?" and the model calls the `get_weather` tool:

```
Event stream order (top to bottom):

1.  {type: "reasoning",      data: "The user wants to know the weather in Beijing..."}
2.  {type: "content",        data: "Sure, let me check"}
3.  {type: "content",        data: "the weather in Beijing."}
4.  {type: "tool_call_delta", data: {index: 0, id: "call_1", name: "get_", arguments: ""}}
5.  {type: "tool_call_delta", data: {index: 0, id: "", name: "weather", arguments: '{"city": "'}}
6.  {type: "tool_call_delta", data: {index: 0, id: "", name: "", arguments: 'Beijing"'}'}
7.  {type: "tool_call",       data: {id: "call_1", function: {name: "get_weather", arguments: '{"city": "Beijing"'}'}}}
8.  {type: "tool_result",     data: {name: "get_weather", result: "Beijing: Sunny, 22°C"}}
    ── Tool execution complete, automatically continues API call ──
9.  {type: "content",        data: "The current weather in Beijing is sunny"}
10. {type: "content",        data: ", with a temperature of 22°C."}
11. {type: "done",           data: "The current weather in Beijing is sunny, with a temperature of 22°C."}
```

### Common Processing Patterns

#### Pattern 1: Typewriter Effect + Tool Progress

```python
for event in agent.stream_msg("Weather and timezone info for Beijing"):
    if event["type"] == "content":
        print(event["data"], end="", flush=True)
    elif event["type"] == "reasoning":
        print(f"\n\033[2m[Thinking...]\033[0m", end="", flush=True)
    elif event["type"] == "tool_call_delta":
        if event["data"]["name"]:            # Only print when the name appears
            print(f"\n\033[33m[🛠 Calling: {event['data']['name']}]\033[0m", end="", flush=True)
    elif event["type"] == "tool_result":
        print(f"\n\033[32m[✅ {event['data']['name']} returned: {event['data']['result'][:50]}...]\033[0m")
    elif event["type"] == "done":
        print()  # Newline
```

#### Pattern 2: Focus Only on Final Result

```python
full_text = ""
for event in agent.stream_msg("Weather in Beijing"):
    if event["type"] == "content":
        full_text += event["data"]
    elif event["type"] == "done":
        full_text = event["data"]  # Directly take the full text
print(full_text)
```

#### Pattern 3: Headless Background Run (Capture Tool Calls Only)

```python
tool_results = []
for event in agent.stream_msg("Check the database"):
    if event["type"] == "tool_result":
        tool_results.append(event["data"])
    elif event["type"] == "done":
        final_answer = event["data"]
```

### Comparison with send_msg_with_tools

| Feature | `send_msg_with_tools` | `stream_output` / `stream_msg` |
|---------|----------------------|-------------------------------|
| Return style | Blocking, returns complete dict | Generator, pushes events incrementally |
| Typewriter effect | ❌ Not possible | ✅ Supported |
| Tool call visibility | Invisible (internal execution) | ✅ Observable at every stage |
| Multi-round tool calls | ✅ Automatic | ✅ Automatic |
| Use cases | Simple calls, background tasks | Interactive interfaces, progress display |

---

## Detailed Documentation

### AIBot

`AIBot` is the core class for interacting with AI models.

#### Initialization

```python
AIBot(
    api_key: str | None = None,         # API Key; defaults to OPENAI_API_KEY env var
    base_url: str | None = None,         # Custom API address (for compatible interfaces)
    model: str = "gpt-4o",              # Model name
    system_prompt: str | None = None,    # System prompt
    max_tool_rounds: int = 10,           # Maximum tool call rounds to prevent dead loops
    temperature: float = 0.7,            # Sampling temperature, controls generation randomness (0~2)
)
```

#### Methods

| Method | Return Value | Description |
|--------|--------------|-------------|
| `send_msg(message, tools=None)` | `dict` | Send a message, returns full response `{content, tool_calls, finish_reason}` |
| `send_msg_with_tools(message, tools, tool_executor=None)` | `dict` | Send message + automatic tool calling loop |
| `stream_output(message, tools=None, tool_executor=None)` | `Generator[dict]` | **Core feature** Streaming output, supports text + tool calls simultaneously |
| `reset()` | `None` | Reset conversation history (preserves system prompt) |
| `history` | `list[dict]` | Get a read-only copy of the full conversation history |

---

### Agent

`Agent` is a high-level wrapper that combines `AIBot` + `Tools`, treating the bot and tools as a single unit to simplify calls.

#### Initialization

```python
Agent(
    bot: AIBot,    # AIBot instance
    tools: Tools,  # Tools instance
)
```

#### Methods

| Method | Return Value | Description |
|--------|--------------|-------------|
| `send_msg(msg)` | `dict` | Send a message, automatically handles tool calling loop, returns `{content, finish_reason, tool_rounds}` |
| `stream_msg(msg)` | `Generator[dict]` | Stream a message, automatically handles text deltas and tool calls |

`send_msg` internally calls `bot.send_msg_with_tools(msg, self.tools)`, automatically using registered tools.
`stream_msg` internally calls `bot.stream_output(msg, self.tools.definitions(), self.tools.execute)`, with event types identical to `stream_output`.

#### Example

```python
from ai_util import AIBot, Tools, Agent

tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """Get the weather for a specified city"""
    return f"{city}: Sunny, 25°C"

@tools.add
def get_timezone(city: str) -> str:
    """Get the timezone for a specified city"""
    zones = {"Beijing": "UTC+8", "Tokyo": "UTC+9"}
    return zones.get(city, "Unknown")

bot = AIBot(api_key="sk-xxx", model="gpt-4o")
agent = Agent(bot=bot, tools=tools)

# Single tool call
result = agent.send_msg("How's the weather in Beijing?")

# Multiple tool calls + streaming
for event in agent.stream_msg("Weather and timezone in Tokyo"):
    if event["type"] == "content":
        print(event["data"], end="")
    elif event["type"] == "tool_call":
        print(f"\n[Calling: {event['data']['function']['name']}]")
    elif event["type"] == "done":
        print("\n[Done]")
```

---

### Tools

`Tools` is a convenient tool registration and management class.

#### Registering Tools

Three registration methods are supported:

**Method 1: Decorator (Recommended)**

```python
tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """Get the weather"""
    return f"{city}: Sunny"
```

Type annotations in the function signature are automatically inferred as JSON Schema, and the function docstring is used as the tool description.

**Method 2: Decorator + Custom Parameters**

```python
@tools.add(
    name="weather",                     # Custom tool name
    description="Get weather info",     # Custom description
    parameters={...},                   # Custom JSON Schema
)
def get_weather(city: str) -> str:
    ...
```

**Method 3: Manual Registration**

```python
def my_func(x: int, y: int) -> int:
    return x + y

tools.add(my_func, name="add", description="Add two numbers")
```

#### Methods

| Method | Return Value | Description |
|--------|--------------|-------------|
| `add(func, *, name, description, parameters)` | `Callable` | Register a tool (decorator / direct call) |
| `remove(name)` | `None` | Remove a tool |
| `get(name)` | `Tool | None` | Get a specific tool |
| `definitions()` | `list[dict]` | Get an OpenAI-compatible list of tool definitions |
| `execute(name, arguments)` | `Any` | Execute a tool |
| `__call__(name, arguments)` | `Any` | Convenient alias for execution |

#### Tool Object

```python
Tool(
    name: str,                          # Tool name
    description: str,                   # Tool description
    handler: Callable,                  # Handler function
    parameters: dict | None = None,     # Custom parameter schema
)
```

- `tool.definition()` — Generate a single OpenAI tool definition
- `tool.execute(**kwargs)` — Execute the tool

---

### Sandbox

`Sandbox` is a built-in sandbox toolkit providing file I/O, system command execution, HTTP requests, and other common environment interaction capabilities. Via `register_tools(tools)`, all sandbox tools can be registered to a `Tools` instance with one click, giving AI the ability to interact with the local environment.

#### Initialization

```python
Sandbox(
    sandbox_dir: str,                          # Sandbox root directory
    allow_file_access: bool = True,            # Whether to allow file access
    allow_network_access: bool = True,         # Whether to allow network access
    allow_raw_network_data: bool = True,       # Whether to allow raw network data read/write
    allow_syscmd_access: bool = False,         # Whether to allow system command execution
    file_access_mode: int = 1,                 # 0: sandbox only, 1: progressive, 2: full access
    file_progressive_access_mode: int = 0,     # 0: whitelist, 1: blacklist (only effective when mode=1)
    file_progressive_access_list: list = [],   # Progressive access file path list
)
```

#### File Access Modes

| Mode | Value | Description |
|------|-------|-------------|
| **Sandbox Only** | `0` | Can only access files under `sandbox_dir` (safest) |
| **Progressive** | `1` | Controls additional access paths via whitelist/blacklist |
| **Full Access** | `2` | Can access any path in the system (most flexible, highest risk) |

#### Registering Sandbox Tools

```python
from ai_util import AIBot, Tools, Agent, Sandbox

tools = Tools()
sandbox = Sandbox("/home/user/project", allow_syscmd_access=True)
sandbox.register_tools(tools)

agent = Agent(bot=AIBot(model="gpt-4o"), tools=tools)
```

#### Sandbox Tool List

After registration, AI can use the following tools:

| Tool Name | Description | Required Permission |
|-----------|-------------|---------------------|
| `read_file` | Read file contents | File read |
| `readlines` | Read a specified line range | File read |
| `write_file` | Write / overwrite a file | File write |
| `write_lines` | Overwrite multiple lines at a specified position | File write |
| `insert_lines` | Insert content before a specified line | File write |
| `run_syscmd` | Run system commands | `allow_syscmd_access=True` |
| `get_request` | Send HTTP GET | `allow_raw_network_data=True` |
| `head_request` | Send HTTP HEAD | `allow_raw_network_data=True` |
| `post_request` | Send HTTP POST | `allow_raw_network_data=True` |
| `put_request` | Send HTTP PUT | `allow_raw_network_data=True` |
| `delete_request` | Send HTTP DELETE | `allow_raw_network_data=True` |
| `options_request` | Send HTTP OPTIONS | `allow_raw_network_data=True` |
| `listdir` | List files and subdirectories in a directory | File read |
| `get_sandbox_dir` | Get the current sandbox root directory path | None (returns config info only) |

#### Example: Secure Code Review Assistant

```python
from ai_util import AIBot, Tools, Agent, Sandbox

# Restrict AI to only reading the project directory, disable network and system commands
tools = Tools()
sandbox = Sandbox(
    "/home/user/my-project",
    allow_file_access=True,
    allow_network_access=False,
    allow_syscmd_access=False,
)
sandbox.register_tools(tools)

bot = AIBot(api_key="sk-xxx", model="gpt-4o", system_prompt="You are a code review assistant.")
agent = Agent(bot=bot, tools=tools)

# AI can only read files under my-project, cannot access the network or execute commands
result = agent.send_msg("Please review the code quality of main.py and utils.py")
print(result["content"])
```

#### Example: Development Assistant with Network Access Allowed

```python
sandbox = Sandbox(
    "/home/user/workspace",
    allow_syscmd_access=True,           # Allow running git, npm, etc.
    allow_raw_network_data=True,        # Allow calling APIs, downloading dependencies
)
```

---

## Advanced Usage

### Using Compatible APIs (DeepSeek / Tongyi Qianwen / GLM)

```python
bot = AIBot(
    api_key="sk-xxx",
    base_url="https://api.deepseek.com",    # Or other compatible API address
    model="deepseek-chat",                  # Corresponding platform model name
)
```

### Multi-Round Tool Calls

`send_msg_with_tools`, `stream_output`, and `Agent.send_msg` automatically handle multi-round tool calls:

```python
# Tools can be called multiple times; the model decides whether to call again based on results
result = agent.send_msg("Check the weather in Beijing and Shanghai for me, then compare them")
```

### Manually Managing Conversation History

```python
bot.reset()                         # Clear conversation (preserves system prompt)
history = bot.history               # Get a copy of the message list
```

### Custom Tool Parameter Schema

When automatic inference is insufficient, you can manually provide a complete JSON Schema:

```python
@tools.add(parameters={
    "type": "object",
    "properties": {
        "city": {
            "type": "string",
            "description": "City name, e.g. Beijing, Shanghai",
            "enum": ["Beijing", "Shanghai", "Guangzhou", "Shenzhen"],
        },
        "units": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"],
            "default": "celsius",
        },
    },
    "required": ["city"],
})
def get_weather(city: str, units: str = "celsius") -> str:
    ...
```

---

## Project Structure

```
ai-util/
├── src/
│   └── ai_util/
│       ├── __init__.py       # Package entry, exports AIBot, Tool, Tools, Agent, Sandbox
│       ├── __about__.py      # Version info
│       ├── agent.py          # Agent high-level wrapper
│       ├── bot.py            # AIBot main class
│       ├── tools.py          # Tools wrapper
│       └── sandbox.py        # Sandbox toolkit
├── tests/
│   └── test_agent_sandbox.py # Agent + Sandbox integration tests
├── pyproject.toml
├── pyrightconfig.json        # Strict mode configuration
└── README.md
```

---

## Development

```bash
# Clone the project
git clone https://github.com/BaoShuWen/ai-util.git
cd ai-util

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type checking
pyright src/ai_util/
```

---

## License

`ai-util` is open-sourced under the MIT License.

Copyright © 2026-present BaoShuWen
