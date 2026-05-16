#!/usr/bin/env python3
"""
test_agent.py — Agent 类集成测试

测试场景:
  1. 基础 send_msg（非流式）
  2. stream_msg（流式）
  3. 工具调用自动执行

运行:
  python test_agent.py
"""

import os
import sys
import json

# ── 确保使用本地源码 ──────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, SRC_DIR)

from ai_util.agent import Agent
from ai_util.bot import AIBot
from ai_util.tools import Tools


# ══════════════════════════════════════════════════════════
# 配置区
# ══════════════════════════════════════════════════════════

API_KEY = "sk-99def4ffa01a4645816f228b258c1a65"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"  # DeepSeek 的对话模型


# ══════════════════════════════════════════════════════════
# 测试工具定义
# ══════════════════════════════════════════════════════════

def build_weather_tools() -> Tools:
    """构建测试用的工具集"""
    tools = Tools()

    @tools.add
    def get_weather(city: str) -> str:
        """获取指定城市的当前天气"""
        data = {
            "北京": "晴, 22°C, 湿度 30%",
            "上海": "多云, 26°C, 湿度 65%",
            "深圳": "雷阵雨, 30°C, 湿度 85%",
            "杭州": "阴, 24°C, 湿度 70%",
        }
        return data.get(city, f"暂无 {city} 的天气数据")

    @tools.add
    def get_time(city: str = "北京") -> str:
        """获取指定城市的当前时间（时区信息）"""
        zones = {
            "北京": "UTC+8 (北京时间)",
            "东京": "UTC+9 (日本标准时间)",
            "纽约": "UTC-5 (美国东部时间)",
            "伦敦": "UTC+0 (格林威治标准时间)",
        }
        return zones.get(city, f"未知时区: {city}")

    return tools


# ══════════════════════════════════════════════════════════
# 测试用例
# ══════════════════════════════════════════════════════════

SEP = "─" * 60


def test_send_msg(agent: Agent):
    """测试 1: 非流式消息发送"""
    print(f"\n{SEP}")
    print("  📨 测试 1: send_msg（非流式）")
    print(f"{SEP}")

    result = agent.send_msg("北京的天气怎么样？")

    print(f"  💬 回复: {result.get('content', '')}")
    print(f"  🏁 finish_reason: {result.get('finish_reason')}")
    print(f"  🔄 tool_rounds: {result.get('tool_rounds')}")

    assert result.get("content"), "❌ 内容为空"
    assert "北京" in result.get("content", ""), "❌ 未提及北京"
    print("  ✅ 通过")


def test_stream_msg(agent: Agent):
    """测试 2: 流式消息发送"""
    print(f"\n{SEP}")
    print("  📨 测试 2: stream_msg（流式）")
    print(f"{SEP}")

    full_text = ""
    tool_call_count = 0

    for event in agent.stream_msg("上海今天天气和时区信息都要"):
        if event["type"] == "content":
            full_text += event["data"]
        elif event["type"] == "tool_call":
            name = event["data"]["function"]["name"]
            print(f"  🛠  工具调用: {name}")
            tool_call_count += 1
        elif event["type"] == "tool_result":
            print(f"  ✅ 工具结果: {event['data']['result'][:60]}...")
        elif event["type"] == "done":
            print(f"  ✅ 流结束")
        elif event["type"] == "error":
            print(f"  ❌ 错误: {event['data']}")

    print(f"  💬 完整回复: {full_text}")
    print(f"  🛠  工具调用次数: {tool_call_count}")
    assert full_text, "❌ 流式回复内容为空"
    print("  ✅ 通过")


def test_no_tool_msg(agent: Agent):
    """测试 3: 不需要工具调用的纯对话"""
    print(f"\n{SEP}")
    print("  📨 测试 3: 纯对话（无需工具）")
    print(f"{SEP}")

    result = agent.send_msg("你好，请做一下自我介绍")

    content = result.get("content", "")
    print(f"  💬 回复: {content}")
    assert content, "❌ 内容为空"
    assert result["finish_reason"] == "stop", "❌ 非正常结束"
    print("  ✅ 通过")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════

def main():
    print("╔" + "═" * 58 + "╗")
    print("║       Agent 类集成测试套件                          ║")
    print("║       模型: deepseek-chat                           ║")
    print("║       API:  api.deepseek.com                       ║")
    print("╚" + "═" * 58 + "╝")

    # 构建组件
    print("\n  🔧 初始化 AIBot...")
    bot = AIBot(
        api_key=API_KEY,
        base_url=BASE_URL,
        model=MODEL,
        system_prompt="你是一个有用的助手，可以使用天气和时区工具回答用户问题。",
    )

    print("  🔧 注册测试工具...")
    tools = build_weather_tools()
    print(f"     已注册工具: {list(tools._tools.keys())}")

    print("  🔧 创建 Agent...")
    agent = Agent(bot=bot, tools=tools)

    # 运行测试
    passed = 0
    failed = 0

    for test_fn in [test_send_msg, test_stream_msg, test_no_tool_msg]:
        try:
            test_fn(agent)
            passed += 1
        except Exception as e:
            print(f"  ❌ 测试失败: {e}")
            failed += 1

    # 汇总
    print(f"\n{SEP}")
    print(f"  📊 汇总: {passed} 通过, {failed} 失败, "
          f"共 {passed + failed} 项")
    print(f"{SEP}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
