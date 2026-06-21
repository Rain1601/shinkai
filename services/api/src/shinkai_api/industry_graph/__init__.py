"""Industry graph module — multi-facet supply-chain knowledge graph.

V0 surface: Pydantic schemas. Store, tools, and DeepSeek-driven ingestion land
in later stages.
"""

from __future__ import annotations

from . import schemas, store, tools
from .agent_loop import AGENT_SYSTEM_PROMPT, AgentLoop
from .e2e_runner import INGESTION_SYSTEM_PROMPT, ToolDispatcher
from .service import IndustryGraphStore
from .tools import build_tools, register_industry_graph_tools

__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "AgentLoop",
    "INGESTION_SYSTEM_PROMPT",
    "IndustryGraphStore",
    "ToolDispatcher",
    "build_tools",
    "register_industry_graph_tools",
    "schemas",
    "store",
    "tools",
]
