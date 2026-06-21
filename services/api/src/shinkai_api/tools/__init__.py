from shinkai_api.tools.base import Tool, ToolRegistry, ToolResult, default_tool_registry
from shinkai_api.tools.fxbg import FxbgParagraphsTool, FxbgPdfUrlTool, FxbgSearchTool
from shinkai_api.tools.sec_edgar import SECFilingsTool
from shinkai_api.tools.ticker_validator import TickerValidatorTool
from shinkai_api.tools.web import WebExtractTool, WebSearchTool

default_tool_registry.register(WebSearchTool())
default_tool_registry.register(WebExtractTool())
default_tool_registry.register(TickerValidatorTool())
default_tool_registry.register(SECFilingsTool())
default_tool_registry.register(FxbgSearchTool())
default_tool_registry.register(FxbgParagraphsTool())
default_tool_registry.register(FxbgPdfUrlTool())

__all__ = [
    "FxbgParagraphsTool",
    "FxbgPdfUrlTool",
    "FxbgSearchTool",
    "SECFilingsTool",
    "TickerValidatorTool",
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "WebExtractTool",
    "WebSearchTool",
    "default_tool_registry",
]
