# ai-util

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ai-util** 是一个实用、优雅的 AI 封装工具包，采用 OOP 风格设计，基于 OpenAI SDK 构建。让你用更少的代码、更清晰的接口与 AI 模型交互。

### 核心特性

- **🎯 简洁 OOP 设计** — `AIBot` 主类 + `Tools` 工具集 + `Agent` 高级封装，开箱即用
- **📡 流式 + 工具调用同时支持** — 在同一个流里同时接收文本增量和工具调用增量，工具执行完毕后自动继续对话
- **🔧 自动工具注册** — 装饰器注册工具函数，自动从类型注解推断参数 Schema
- **🔄 自动工具循环** — `send_msg_with_tools` 一行搞定工具调用→执行→继续对话的完整循环
- **🤖 Agent 高级封装** — `Agent` 类将 `AIBot` 与 `Tools` 绑定，简化调用
- **📝 对话历史管理** — 自动维护消息列表，支持重置和导出
- **🔗 兼容任意 OpenAI 接口** — 支持 DeepSeek、通义千问、GLM 等兼容 API

---

## 安装

```bash
pip install git+https://github.com/zaf-x/ai-util.git
```

需要 Python 3.8+ 和 `openai>=1.0.0`。

## 快速开始

### 基础对话

```python
from ai_util import AIBot

bot = AIBot(
    api_key="sk-xxx",                # 或设置环境变量 OPENAI_API_KEY
    model="gpt-4o",
    system_prompt="你是一个有用的助手。",
)

# 非流式
resp = bot.send_msg("你好！")
print(resp["content"])

# 流式
for chunk in bot.stream_output("给我讲个故事"):
    if chunk["type"] == "content":
        print(chunk["data"], end="", flush=True)
```

### 使用工具

```python
from ai_util import AIBot, Tools

tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """获取指定城市的天气"""
    return f"{city}: 晴, 25°C, 微风"

bot = AIBot(model="gpt-4o")
result = bot.send_msg_with_tools("北京天气怎么样？", tools)
print(result["content"])
```

### 使用 Agent（高级封装）

```python
from ai_util import AIBot, Tools, Agent

tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """获取指定城市的天气"""
    return f"{city}: 晴, 25°C, 微风"

bot = AIBot(
    api_key="sk-xxx",
    model="gpt-4o",
    system_prompt="你是一个有用的助手。",
)

agent = Agent(bot=bot, tools=tools)

# 非流式 — 自动执行工具
result = agent.send_msg("北京天气怎么样？")
print(result["content"])

# 流式 — 文本 + 工具调用同时处理
for event in agent.stream_msg("上海天气怎么样？"):
    if event["type"] == "content":
        print(event["data"], end="", flush=True)
    elif event["type"] == "tool_call":
        print(f"\n[正在调用 {event['data']['function']['name']}]")
    elif event["type"] == "tool_result":
        print(f"\n[工具返回: {event['data']['result']}]")
```

---

## 流式输出详解

这是 `ai-util` 的核心特性：**在一个流中同时处理文本输出和工具调用**，工具执行完毕后自动继续对话，无需手动管理循环。

### 工作原理

`stream_output`（及 `Agent.stream_msg`）的内部流程：

```
用户消息
    │
    ▼
┌──────────────────┐
│  调用 AI API      │  ← 流式模式
│  (stream=True)    │
└────────┬─────────┘
         │
    ┌────┴────┐
    │ 文本增量  │  → yield {"type": "content", "data": "..."}
    └────┬────┘
         │
    ┌────┴────┐
    │ 工具调用  │  → yield {"type": "tool_call_delta", ...}
    │ 增量     │     yield {"type": "tool_call", ...}
    └────┬────┘
         │
    ┌────┴────┐
    │ 执行工具  │  → yield {"type": "tool_result", ...}
    │ (本地)   │     自动追加到对话历史
    └────┬────┘
         │
    ┌────┴────┐
    │ 继续调用  │  ← 递归：AI 可能再次调用工具
    │ API      │     或返回最终文本
    └────┬────┘
         │
    ┌────┴────┐
    │ 流结束    │  → yield {"type": "done", "data": "..."}
    └─────────┘
```

**关键行为：**
- 工具调用在本地执行（不经过 API），结果立即送回对话
- 多轮工具调用自动递归，直到模型不再请求工具
- `max_tool_rounds` 参数防止无限循环（默认 10 轮）

### 事件类型详解

每个事件是一个 `dict`，包含 `type` 标识事件类别和 `data` 携带数据：

#### content — 文本增量

```python
{
    "type": "content",
    "data": "北京"           # 逐字/逐段推送的文本片段
}
```

模型生成的文本以增量形式逐块推送。调用方应将所有 `content` 事件拼接以得到完整文本。

#### reasoning — 推理过程（某些模型支持）

```python
{
    "type": "reasoning",
    "data": "让我查一下北京的天气..."   # 模型的推理过程/思考链
}
```

部分模型（如 DeepSeek-R1）在输出最终答案前会输出推理过程。此事件与 `content` 事件交错出现。

#### tool_call_delta — 工具调用增量

```python
{
    "type": "tool_call_delta",
    "data": {
        "index": 0,          # 工具调用索引（同一轮可能有多个工具）
        "id": "call_abc",    # 调用 ID，首次出现时非空，后续增量可能为空
        "name": "get_",      # 工具名增量（可能分多次推送）
        "arguments": '{"ci'  # 参数 JSON 增量（可能分多次推送）
    }
}
```

当模型决定调用工具时，工具名和参数以增量形式推送。通常用于展示实时进度（如打字机效果的 `[正在调用 get_weather...]`）。

**注意：** `name` 和 `arguments` 是增量拼接的，直接使用可能不完整。如需完整数据，应使用 `tool_call` 事件。

#### tool_call — 完整工具调用

```python
{
    "type": "tool_call",
    "data": {
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": "{\"city\": \"北京\"}"
        }
    }
}
```

当流结束且工具调用已收集完整时触发。此时 `arguments` 是完整的 JSON 字符串，可直接解析使用。

#### tool_result — 工具执行结果

```python
{
    "type": "tool_result",
    "data": {
        "name": "get_weather",
        "result": "北京: 晴, 22°C, 湿度 30%"   # 工具函数的返回值（字符串化）
    }
}
```

工具在本地执行完毕后触发。`result` 是工具函数的返回值经 `json.dumps` 序列化后的字符串，或直接是字符串。

#### done — 流结束

```python
{
    "type": "done",
    "data": "北京的天气是..."   # 本轮所有文本增量的最终拼接结果
}
```

流式输出完全结束，不再有更多事件。`data` 是完整的最终回复文本。

#### error — 错误

```python
{
    "type": "error",
    "data": "工具调用超过最大轮次 (10)"
}
```

发生不可恢复的错误时触发。之后流结束，不再有其他事件。

### 事件类型速查表

| type | data 类型 | data 内容 | 触发时机 |
|------|-----------|-----------|---------|
| `"content"` | `str` | 文本片段 | 模型生成文本时逐块推送 |
| `"reasoning"` | `str` | 推理过程文本 | 模型思考时推送（部分模型支持） |
| `"tool_call_delta"` | `dict` | `{index, id, name, arguments}` | 工具调用流式增量 |
| `"tool_call"` | `dict` | `{id, type, function: {name, arguments}}` | 工具调用完整数据就绪时 |
| `"tool_result"` | `dict` | `{name, result}` | 工具执行完毕后 |
| `"done"` | `str` | 完整回复文本 | 流完全结束时 |
| `"error"` | `str` | 错误描述 | 发生不可恢复错误时 |

### 完整事件流示例

假设用户问 "北京天气怎么样？"，且模型调用了 `get_weather` 工具：

```
事件流顺序（时间从上到下）：

1.  {type: "reasoning",      data: "用户想知道北京的天气..."}
2.  {type: "content",        data: "好的，我来查一下"}
3.  {type: "content",        data: "北京的天气。"}
4.  {type: "tool_call_delta", data: {index: 0, id: "call_1", name: "get_", arguments: ""}}
5.  {type: "tool_call_delta", data: {index: 0, id: "", name: "weather", arguments: '{"city": "'}}
6.  {type: "tool_call_delta", data: {index: 0, id: "", name: "", arguments: '北京"}'}}
7.  {type: "tool_call",       data: {id: "call_1", function: {name: "get_weather", arguments: '{"city": "北京"}'}}}
8.  {type: "tool_result",     data: {name: "get_weather", result: "北京: 晴, 22°C"}}
    ── 工具执行完毕，自动继续调用 API ──
9.  {type: "content",        data: "北京当前天气晴朗"}
10. {type: "content",        data: "，温度22°C。"}
11. {type: "done",           data: "北京当前天气晴朗，温度22°C。"}
```

### 常见处理模式

#### 模式一：打字机效果 + 工具进度

```python
for event in agent.stream_msg("北京的天气和时区信息"):
    if event["type"] == "content":
        print(event["data"], end="", flush=True)
    elif event["type"] == "reasoning":
        print(f"\n\033[2m[思考中...]\033[0m", end="", flush=True)
    elif event["type"] == "tool_call_delta":
        if event["data"]["name"]:            # 只在名字出现时打印
            print(f"\n\033[33m[🛠 调用: {event['data']['name']}]\033[0m", end="", flush=True)
    elif event["type"] == "tool_result":
        print(f"\n\033[32m[✅ {event['data']['name']} 返回: {event['data']['result'][:50]}...]\033[0m")
    elif event["type"] == "done":
        print()  # 换行
```

#### 模式二：仅关注最终结果

```python
full_text = ""
for event in agent.stream_msg("北京的天气"):
    if event["type"] == "content":
        full_text += event["data"]
    elif event["type"] == "done":
        full_text = event["data"]  # 直接取完整文本
print(full_text)
```

#### 模式三：无界面后台运行（仅捕获工具调用）

```python
tool_results = []
for event in agent.stream_msg("查一下数据库"):
    if event["type"] == "tool_result":
        tool_results.append(event["data"])
    elif event["type"] == "done":
        final_answer = event["data"]
```

### 与 send_msg_with_tools 的对比

| 特性 | `send_msg_with_tools` | `stream_output` / `stream_msg` |
|------|----------------------|-------------------------------|
| 返回方式 | 阻塞，返回完整 dict | 生成器，逐事件推送 |
| 打字机效果 | ❌ 无法 | ✅ 支持 |
| 工具调用可见性 | 不可见（内部执行） | ✅ 可观察到每个阶段 |
| 多轮工具调用 | ✅ 自动 | ✅ 自动 |
| 适用场景 | 简单调用、后台任务 | 交互式界面、进度展示 |

---

## 详细文档

### AIBot

`AIBot` 是与 AI 模型交互的核心类。

#### 初始化

```python
AIBot(
    api_key: str | None = None,         # API Key，默认读取 OPENAI_API_KEY 环境变量
    base_url: str | None = None,         # 自定义 API 地址（兼容接口用）
    model: str = "gpt-4o",              # 模型名称
    system_prompt: str | None = None,    # 系统提示词
    max_tool_rounds: int = 10,           # 最大工具调用轮次，防死循环
)
```

#### 方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `send_msg(message, tools=None)` | `dict` | 发送消息，返回完整响应 `{content, tool_calls, finish_reason}` |
| `send_msg_with_tools(message, tools, tool_executor=None)` | `dict` | 发送消息 + 自动工具调用循环 |
| `stream_output(message, tools=None, tool_executor=None)` | `Generator[dict]` | **核心特性** 流式输出，支持文本 + 工具调用同时处理 |
| `reset()` | `None` | 重置对话历史（保留 system prompt） |
| `history` | `list[dict]` | 获取完整对话历史（只读副本） |

---

### Agent

`Agent` 是 `AIBot` + `Tools` 的高级封装，将 bot 和 tools 组合为一个整体，简化调用。

#### 初始化

```python
Agent(
    bot: AIBot,    # AIBot 实例
    tools: Tools,  # Tools 实例
)
```

#### 方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `send_msg(msg)` | `dict` | 发送消息，自动调用工具循环，返回 `{content, finish_reason, tool_rounds}` |
| `stream_msg(msg)` | `Generator[dict]` | 流式发送消息，自动处理文本增量与工具调用 |

`send_msg` 内部调用 `bot.send_msg_with_tools(msg, self.tools)`，自动使用已注册的工具。
`stream_msg` 内部调用 `bot.stream_output(msg, self.tools.definitions(), self.tools.execute)`，事件类型与 `stream_output` 完全一致。

#### 示例

```python
from ai_util import AIBot, Tools, Agent

tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """获取指定城市的天气"""
    return f"{city}: 晴, 25°C"

@tools.add
def get_timezone(city: str) -> str:
    """获取指定城市的时区"""
    zones = {"北京": "UTC+8", "东京": "UTC+9"}
    return zones.get(city, "未知")

bot = AIBot(api_key="sk-xxx", model="gpt-4o")
agent = Agent(bot=bot, tools=tools)

# 单次工具调用
result = agent.send_msg("北京天气怎么样？")

# 多次工具调用 + 流式
for event in agent.stream_msg("东京的天气和时区"):
    if event["type"] == "content":
        print(event["data"], end="")
    elif event["type"] == "tool_call":
        print(f"\n[调用: {event['data']['function']['name']}]")
    elif event["type"] == "done":
        print("\n[完成]")
```

---

### Tools

`Tools` 是便捷的工具注册和管理类。

#### 注册工具

支持三种注册方式：

**方式一：装饰器（推荐）**

```python
tools = Tools()

@tools.add
def get_weather(city: str) -> str:
    """获取天气"""
    return f"{city}: 晴"
```

函数签名中的类型注解会被自动推断为 JSON Schema，函数文档字符串作为工具描述。

**方式二：装饰器 + 自定义参数**

```python
@tools.add(
    name="weather",                     # 自定义工具名
    description="获取天气信息",          # 自定义描述
    parameters={...},                   # 自定义 JSON Schema
)
def my_weather(city: str) -> str:
    ...
```

**方式三：手动注册**

```python
def my_func(x: int, y: int) -> int:
    return x + y

tools.add(my_func, name="add", description="两数相加")
```

#### 方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `add(func, *, name, description, parameters)` | `Callable` | 注册工具（装饰器/直接调用） |
| `remove(name)` | `None` | 移除工具 |
| `get(name)` | `Tool | None` | 获取指定工具 |
| `definitions()` | `list[dict]` | 获取 OpenAI 兼容的工具定义列表 |
| `execute(name, arguments)` | `Any` | 执行工具 |
| `__call__(name, arguments)` | `Any` | 便捷调用别名 |

#### Tool 对象

```python
Tool(
    name: str,                          # 工具名称
    description: str,                   # 工具描述
    handler: Callable,                  # 处理函数
    parameters: dict | None = None,     # 自定义参数 Schema
)
```

- `tool.definition()` — 生成单条 OpenAI 工具定义
- `tool.execute(**kwargs)` — 执行工具

---

## 进阶用法

### 使用兼容 API（DeepSeek / 通义千问 / GLM）

```python
bot = AIBot(
    api_key="sk-xxx",
    base_url="https://api.deepseek.com",    # 或其他兼容 API 地址
    model="deepseek-chat",                  # 对应平台的模型名
)
```

### 多轮工具调用

`send_msg_with_tools`、`stream_output` 和 `Agent.send_msg` 会自动处理多轮工具调用：

```python
# 工具可以调用多次，模型会根据结果决定是否再次调用工具
result = agent.send_msg("帮我查一下北京和上海的天气，然后对比一下")
```

### 手动管理对话历史

```python
bot.reset()                         # 清空对话（保留 system prompt）
history = bot.history               # 获取消息列表副本
```

### 自定义工具参数 Schema

当自动推断不满足需求时，可以手动提供完整 JSON Schema：

```python
@tools.add(parameters={
    "type": "object",
    "properties": {
        "city": {
            "type": "string",
            "description": "城市名称，如 北京、上海",
            "enum": ["北京", "上海", "广州", "深圳"],
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

## 项目结构

```
ai-util/
├── src/
│   └── ai_util/
│       ├── __init__.py       # 包入口，导出 AIBot, Tool, Tools, Agent
│       ├── __about__.py      # 版本信息
│       ├── agent.py          # Agent 高级封装
│       ├── bot.py            # AIBot 主类
│       └── tools.py          # Tools 工具封装
├── tests/
│   ├── __init__.py
│   ├── test_agent.py         # Agent 集成测试
│   ├── test_bot.py           # AIBot 单元测试（mock）
│   └── test_tools.py         # Tools 单元测试
├── pyproject.toml
├── pyrightconfig.json        # Strict 模式配置
└── README.md
```

---

## 开发

```bash
# 克隆项目
git clone https://github.com/zaf-x/ai-util.git
cd ai-util

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 类型检查
pyright src/ai_util/
```

---

## 许可证

`ai-util` 使用 MIT 许可证开源。

版权所有 © 2026-present zaf-x
