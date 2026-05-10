# ai-util

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**ai-util** 是一个实用、优雅的 AI 封装工具包，采用 OOP 风格设计，基于 OpenAI SDK 构建。让你用更少的代码、更清晰的接口与 AI 模型交互。

### 核心特性

- **🎯 简洁 OOP 设计** — `AIBot` 主类 + `Tools` 工具集，开箱即用
- **📡 流式 + 工具调用同时支持** — 在同一个流里同时接收文本增量和工具调用增量，工具执行完毕后自动继续对话
- **🔧 自动工具注册** — 装饰器注册工具函数，自动从类型注解推断参数 Schema
- **🔄 自动工具循环** — `send_msg_with_tools` 一行搞定工具调用→执行→继续对话的完整循环
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

### 流式 + 工具调用（核心特性）

```python
from ai_util import AIBot, Tools

tools = Tools()

@tools.add
def search_db(query: str) -> str:
    """搜索数据库"""
    return f"查到: {query} 的相关结果"

bot = AIBot(model="gpt-4o")

for event in bot.stream_output(
    "帮我查一下数据",
    tools.definitions(),
    tools.execute,
):
    if event["type"] == "content":
        print(event["data"], end="", flush=True)
    elif event["type"] == "tool_call_delta":
        if event["data"]["name"]:
            print(f"\n[正在调用 {event['data']['name']}]")
    elif event["type"] == "tool_result":
        print(f"\n[工具返回: {event['data']['result']}]")
    elif event["type"] == "done":
        print("\n✅ 完成")
```

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
    max_tool_rounds: int = 10,           # 最大工具调用轮次
)
```

#### 方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `send_msg(message, tools=None)` | `dict` | 发送消息，返回完整响应 `{content, tool_calls, finish_reason}` |
| `send_msg_with_tools(message, tools, tool_executor=None)` | `dict` | 发送消息 + 自动工具调用循环 |
| `stream_output(message, tools=None, tool_executor=None)` | `Generator[dict]` | 流式输出，支持文本 + 工具调用同时处理 |
| `reset()` | `None` | 重置对话历史（保留 system prompt） |
| `history` | `list[dict]` | 获取完整对话历史（只读副本） |

#### stream_output 事件类型

遍历流式输出时，每个 `event` 是一个 `dict`，包含 `type` 和 `data` 字段：

| type | data | 说明 |
|------|------|------|
| `"content"` | `str` | 文本增量 |
| `"tool_call_delta"` | `dict` | 工具调用增量（含 `index`, `id`, `name`, `arguments`） |
| `"tool_call"` | `dict` | 完整工具调用 |
| `"tool_result"` | `dict` | 工具执行结果 `{name, result}` |
| `"done"` | `str` | 流结束，携带最终完整文本 |
| `"error"` | `str` | 错误信息 |

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
| `get(name)` | `Tool \| None` | 获取指定工具 |
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

`send_msg_with_tools` 和 `stream_output` 会自动处理多轮工具调用：

```python
# 工具可以调用多次，模型会根据结果决定是否再次调用工具
result = bot.send_msg_with_tools(
    "帮我查一下北京和上海的天气，然后对比一下",
    tools,
)
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
│       ├── __init__.py       # 包入口，导出 AIBot, Tool, Tools
│       ├── __about__.py      # 版本信息
│       ├── bot.py            # AIBot 主类
│       └── tools.py          # Tools 工具封装
├── tests/
│   ├── __init__.py
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
