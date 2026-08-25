from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict          # JSON schema
    handler: Callable          # 实际执行的函数
    source: str = "native"     # "native" 或 "mcp"

_registered_tools: dict[str, ToolDefinition] = {}

def tool(name: str, description: str, parameters: dict):
    """装饰器，把普通函数注册为可被 LLM 调用的工具"""
    def decorator(func: Callable):
        _registered_tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=func,
            source="native",
        )
        return func
    return decorator

def get_registered_native_tools() -> dict[str, ToolDefinition]:
    return _registered_tools