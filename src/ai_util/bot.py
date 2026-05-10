"""
AIBot - Practical OOP-style AI bot wrapping OpenAI SDK

Features:
  - send_msg: 发送消息并获取完整响应
  - send_msg_with_tools: 发送消息并自动执行工具调用循环
  - stream_output: 流式响应，同时支持文本流 + 工具调用流
  - 自动管理对话历史
"""

import json
from openai import OpenAI
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Union,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_util.tools import Tools


# ------------------------------------------------------------------
# 类型别名
# ------------------------------------------------------------------

Message = Dict[str, Any]
ToolCallDef = Dict[str, Any]
StreamEvent = Dict[str, Any]


# ======================================================================
# AIBot
# ======================================================================


class AIBot:
    """Main AI bot class wrapping OpenAI SDK"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o",
        system_prompt: Optional[str] = None,
        max_tool_rounds: int = 10,
    ) -> None:
        """
        初始化 AI Bot

        Args:
            api_key: OpenAI API key（默认读取 OPENAI_API_KEY 环境变量）
            base_url: 自定义 API 地址（用于兼容接口）
            model: 模型名称
            system_prompt: 系统提示词
            max_tool_rounds: 最大工具调用轮次，防止死循环
        """

        client_kwargs: Dict[str, Any] = {}
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        if base_url is not None:
            client_kwargs["base_url"] = base_url

        self.client: Any = OpenAI(**client_kwargs)
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.messages: List[Message] = []

        if system_prompt is not None:
            self.messages.append({"role": "system", "content": system_prompt})

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _build_kwargs(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """构建通用 API 参数"""
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        return kwargs

    def _package_tool_calls(
        self,
        raw_tool_calls: Any,
    ) -> Optional[List[ToolCallDef]]:
        """将 OpenAI 原始 tool_calls 转成可序列化格式"""
        if not raw_tool_calls:
            return None
        result: List[ToolCallDef] = []
        for tc in raw_tool_calls:
            result.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })
        return result

    def _add_tool_results(
        self,
        tool_calls_list: List[ToolCallDef],
        executor: Callable[[str, Dict[str, Any]], Any],
    ) -> None:
        """执行工具调用并将结果加入对话历史"""
        for tc_data in tool_calls_list:
            func_info = tc_data["function"]
            name: str = func_info["name"]
            raw_args: str = func_info["arguments"]
            try:
                args: Dict[str, Any] = json.loads(raw_args)
            except json.JSONDecodeError as e:
                args = {}
                result: Any = {"error": f"JSON 解析失败: {e}"}
            else:
                try:
                    result = executor(name, args)
                except Exception as e:
                    result = {"error": str(e)}

            content_str: str = (
                json.dumps(result, ensure_ascii=False)
                if not isinstance(result, str)
                else result
            )
            self.messages.append({
                "role": "tool",
                "tool_call_id": tc_data["id"],
                "content": content_str,
            })

    # ------------------------------------------------------------------
    # 核心公开方法
    # ------------------------------------------------------------------

    def send_msg(
        self,
        message: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        发送消息，获取完整响应（非流式）

        Args:
            message: 用户消息
            tools: OpenAI 兼容的工具定义列表

        Returns:
            {"content": str, "tool_calls": list|None, "finish_reason": str}
        """
        self.messages.append({"role": "user", "content": message})

        response = self.client.chat.completions.create(
            **self._build_kwargs(tools),
        )

        choice = response.choices[0]
        msg = choice.message

        self.messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": self._package_tool_calls(msg.tool_calls),
        })

        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls,
            "finish_reason": choice.finish_reason,
        }

    def send_msg_with_tools(
        self,
        message: str,
        tools: Union[List[Dict[str, Any]], "Tools"],
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送消息 + 自动工具调用循环

        自动处理: 工具调用 → 执行 → 继续对话 → 直到模型不再调用工具

        Args:
            message: 用户消息
            tools: 工具定义列表 或 Tools 实例
            tool_executor: 执行函数 fn(name, args) -> result
                          如果 tools 是 Tools 实例且未提供 executor，自动使用 Tools.execute

        Returns:
            {"content": str, "finish_reason": str, "tool_rounds": int}
        """
        # 统一提取工具定义和执行器
        if hasattr(tools, "definitions"):
            tools_obj: Any = tools
            tool_defs: List[Dict[str, Any]] = tools_obj.definitions()
            if tool_executor is None and hasattr(tools_obj, "execute"):
                tool_executor = tools_obj.execute
        else:
            tool_defs = tools  # type: ignore[assignment]

        if tool_executor is None:
            raise ValueError("tools 为普通列表时必须提供 tool_executor")

        self.messages.append({"role": "user", "content": message})

        rounds = 0
        while rounds < self.max_tool_rounds:
            response = self.client.chat.completions.create(
                **self._build_kwargs(tool_defs),
            )

            choice = response.choices[0]
            msg = choice.message
            tool_calls_packed = self._package_tool_calls(msg.tool_calls)

            # 存入助手消息
            assistant_msg: Message = {
                "role": "assistant",
                "content": msg.content,
            }
            if tool_calls_packed is not None:
                assistant_msg["tool_calls"] = tool_calls_packed
            self.messages.append(assistant_msg)

            # 没有工具调用 → 结束
            if not tool_calls_packed:
                return {
                    "content": msg.content,
                    "finish_reason": choice.finish_reason,
                    "tool_rounds": rounds,
                }

            # 执行工具调用
            self._add_tool_results(tool_calls_packed, tool_executor)
            rounds += 1

        return {
            "content": "已达到最大工具调用轮次。",
            "finish_reason": "max_rounds",
            "tool_rounds": rounds,
        }

    def stream_output(
        self,
        message: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> Generator[StreamEvent, None, None]:
        """
        流式输出，同时支持文本流 + 工具调用流

        这是核心特性: 在流式模式下，OpenAI API 同时推送文本增量和工具调用增量。
        工具执行完毕后自动继续对话，调用者无需关心轮次管理。

        Args:
            message: 用户消息
            tools: OpenAI 兼容的工具定义列表
            tool_executor: 执行函数 fn(name, args) -> result

        Yields:
            {"type": "content",       "data": str}         - 文本增量
            {"type": "tool_call_delta","data": dict}       - 工具调用增量
            {"type": "tool_call",     "data": dict}        - 完整工具调用
            {"type": "tool_result",   "data": {"name", "result"}} - 工具结果
            {"type": "done",          "data": str}         - 流结束+最终文本
            {"type": "error",         "data": str}         - 错误信息
        """
        self.messages.append({"role": "user", "content": message})
        yield from self._stream_loop(tools, tool_executor, round_count=0)

    def _stream_loop(
        self,
        tools: Optional[List[Dict[str, Any]]],
        executor: Optional[Callable[[str, Dict[str, Any]], Any]],
        round_count: int,
    ) -> Generator[StreamEvent, None, None]:
        """流式内部循环（递归支持多轮工具调用）"""
        if round_count >= self.max_tool_rounds:
            yield {"type": "error", "data": f"工具调用超过最大轮次 ({self.max_tool_rounds})"}
            return

        stream = self.client.chat.completions.create(
            **self._build_kwargs(tools, stream=True),
        )

        collected_content = ""
        collected_tool_calls: Dict[int, ToolCallDef] = {}

        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # ---- 文本增量 ----
            if delta.content:
                collected_content += delta.content
                yield {"type": "content", "data": delta.content}

            # ---- 工具调用增量 ----
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in collected_tool_calls:
                        collected_tool_calls[idx] = {
                            "id": "",
                            "function": {"name": "", "arguments": ""},
                        }

                    if tc_delta.id:
                        collected_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            collected_tool_calls[idx]["function"]["name"] += (
                                tc_delta.function.name
                            )
                        if tc_delta.function.arguments:
                            collected_tool_calls[idx]["function"]["arguments"] += (
                                tc_delta.function.arguments
                            )

                    yield {
                        "type": "tool_call_delta",
                        "data": {
                            "index": idx,
                            "id": tc_delta.id,
                            "name": tc_delta.function.name if tc_delta.function else None,
                            "arguments": tc_delta.function.arguments
                            if tc_delta.function
                            else None,
                        },
                    }

        # ---- 构建完整的 assistant 消息 ----
        tool_calls_list: List[ToolCallDef] = []
        if collected_tool_calls:
            for idx in sorted(collected_tool_calls):
                tc = collected_tool_calls[idx]
                tool_calls_list.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                })

        assistant_msg: Message = {
            "role": "assistant",
            "content": collected_content or None,
        }
        if tool_calls_list:
            assistant_msg["tool_calls"] = tool_calls_list
        self.messages.append(assistant_msg)

        # ---- 没有工具调用 → 结束 ----
        if not tool_calls_list:
            yield {"type": "done", "data": collected_content}
            return

        # ---- 有工具调用 → 执行并继续 ----
        for tc_data in tool_calls_list:
            yield {"type": "tool_call", "data": tc_data}

        if executor is not None:
            self._add_tool_results(tool_calls_list, executor)
            for tc_data in tool_calls_list:
                yield {
                    "type": "tool_result",
                    "data": {
                        "name": tc_data["function"]["name"],
                        "result": self.messages[-1]["content"],
                    },
                }

            # 递归：继续下一轮
            yield from self._stream_loop(tools, executor, round_count + 1)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置对话历史（保留 system prompt）"""
        system_msgs = [
            m for m in self.messages if m.get("role") == "system"
        ]
        self.messages = system_msgs

    @property
    def history(self) -> List[Message]:
        """获取完整对话历史"""
        return list(self.messages)

    def __repr__(self) -> str:
        return (
            f"AIBot(model={self.model!r}, "
            f"messages={len(self.messages)}, "
            f"max_tool_rounds={self.max_tool_rounds})"
        )
