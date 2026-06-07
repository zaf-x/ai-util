"""
Tools - 便捷的 AI 工具封装

提供干净的方式来定义、注册和执行 AI 工具。
既支持装饰器模式，也支持手动注册，自动生成 OpenAI 兼容的 tool definitions。

Exports:
    Tool, Tools
"""

__all__ = [
    "Tool",
    "Tools",
]

import inspect
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    get_type_hints,
)


# ------------------------------------------------------------------
# 类型映射表（Python type -> JSON Schema type）
# ------------------------------------------------------------------

_TYPE_MAP: Dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _pytype_to_json(ptype: type) -> str:
    """将 Python 类型映射为 JSON Schema 类型字符串"""
    # 处理 typing 模块的泛型（List[str], Dict[str, int] 等）
    origin = getattr(ptype, "__origin__", None)
    if origin is not None and origin in (list, List, dict, Dict):
        return _TYPE_MAP.get(origin, "string")
    # 处理 Union（如 Optional[str]）
    args = getattr(ptype, "__args__", None)
    if args and type(None) in args:
        for arg in args:
            if arg is not type(None):
                return _pytype_to_json(arg)
    # 基础类型
    return _TYPE_MAP.get(ptype, "string")


# ======================================================================
# Tool 类
# ======================================================================


class Tool:
    """单个 AI 工具的定义"""

    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Args:
            name: 工具名称（对 AI 可见）
            description: 工具描述（AI 据此决定是否调用）
            handler: 实际执行的函数
            parameters: 自定义 JSON Schema 参数（None 则从签名自动推断）
        """
        self.name = name
        self.description = description
        self.handler = handler
        self._parameters = parameters

    # ------------------------------------------------------------------

    def definition(self) -> Dict[str, Any]:
        """生成 OpenAI 兼容的工具定义"""
        params = (
            self._parameters if self._parameters is not None
            else self._infer_parameters()
        )
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }

    def _infer_parameters(self) -> Dict[str, Any]:
        """
        从函数签名自动推断 JSON Schema

        支持: 类型注解、默认值、*args/**kwargs（跳过）、文档字符串描述
        """
        sig = inspect.signature(self.handler)
        hints = get_type_hints(self.handler)

        properties: Dict[str, Dict[str, Any]] = {}
        required: List[str] = []

        for pname, param in sig.parameters.items():
            # 跳过 self/cls/*args/**kwargs
            if pname in ("self", "cls"):
                continue
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            ptype = hints.get(pname, str)
            json_type = _pytype_to_json(ptype)

            prop: Dict[str, Any] = {"type": json_type}

            # 有默认值 → 非必需 + 描述默认值
            if param.default is not inspect.Parameter.empty:
                prop["default"] = param.default
                prop["description"] = f"默认: {param.default}"
            else:
                required.append(pname)

            properties[pname] = prop

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def execute(self, **kwargs: Any) -> Any:
        """用给定参数执行工具处理函数"""
        return self.handler(**kwargs)

    def __repr__(self) -> str:
        return f"Tool(name={self.name!r})"


# ======================================================================
# Tools 集合类
# ======================================================================


class Tools:
    """
    便携 AI 工具集封装

    用法示例:

        tools = Tools()

        # 方式一：装饰器（推荐）
        @tools.add
        def get_weather(city: str) -> str:
            \"\"\"获取指定城市的天气\"\"\"
            return f"{city}: 晴, 25°C"

        # 方式二：装饰器 + 自定义参数
        @tools.add(description="搜索网络", parameters={...})
        def search(query: str) -> str:
            return f"搜索结果: {query}"

        # 方式三：手动注册
        def my_func(x: int, y: int) -> int:
            return x + y
        tools.add(my_func, name="add", description="两数相加")

        # 获取定义（给 OpenAI API 用）
        definitions = tools.definitions()

        # 执行工具
        result = tools.execute("get_weather", {"city": "北京"})
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def add(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Callable[..., Any]:
        """
        注册一个工具。可用作装饰器或直接调用。

        装饰器无参数:
            @tools.add
            def my_tool(x: int) -> str: ...

        装饰器带参数:
            @tools.add(name="别名", description="描述")
            def my_tool(x: int) -> str: ...

        直接调用:
            tools.add(my_func, name="别名", description="描述")
        """
        if func is not None:
            return self._register(
                func,
                name=name,
                description=description,
                parameters=parameters,
            )

        # 带参数的装饰器
        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            self._register(
                f,
                name=name,
                description=description,
                parameters=parameters,
            )
            return f

        return decorator

    def _register(
        self,
        func: Callable[..., Any],
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Callable[..., Any]:
        """内部注册逻辑"""
        tool_name = name or func.__name__
        doc = (func.__doc__ or "").strip()
        tool_desc = description or doc or f"工具: {tool_name}"

        self._tools[tool_name] = Tool(
            name=tool_name,
            description=tool_desc,
            handler=func,
            parameters=parameters,
        )
        return func

    # ------------------------------------------------------------------
    # 查询与管理
    # ------------------------------------------------------------------

    def remove(self, name: str) -> None:
        """移除指定工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        """获取指定工具"""
        return self._tools.get(name)

    def definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI 兼容定义列表"""
        return [tool.definition() for tool in self._tools.values()]

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        执行指定工具

        Args:
            name: 工具名称
            arguments: 参数字典 {参数名: 值}

        Returns:
            工具执行结果

        Raises:
            ValueError: 工具不存在时
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(
                f"未知工具: {name!r}。可用工具: {list(self._tools.keys())}"
            )
        return tool.execute(**arguments)

    def __call__(self, name: str, arguments: Dict[str, Any]) -> Any:
        """便捷调用: tools("工具名", {"参数": 值})"""
        return self.execute(name, arguments)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"Tools({list(self._tools.keys())})"
