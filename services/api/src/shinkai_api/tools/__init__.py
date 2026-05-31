from shinkai_api.tools.base import Tool, ToolRegistry, ToolResult, default_tool_registry
from shinkai_api.tools.web import WebExtractTool, WebSearchTool

default_tool_registry.register(WebSearchTool())
default_tool_registry.register(WebExtractTool())

__all__ = [
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "WebExtractTool",
    "WebSearchTool",
    "default_tool_registry",
]
