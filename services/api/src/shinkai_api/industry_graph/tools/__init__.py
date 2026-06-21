"""Industry-graph function tools — 25 callable surfaces for agents.

Tools are not automatically registered with ``default_tool_registry``;
callers (e.g. the FastAPI app, the harness wiring) instantiate the store and
call :func:`register_industry_graph_tools` to bind them.
"""

from __future__ import annotations

from shinkai_api.tools.base import ToolRegistry

from ..service import IndustryGraphStore
from . import analysis_write, audit_snapshot, entity_write, query, relation_write

ALL_TOOL_CLASSES = (
    # Query (9)
    query.FindEntityTool,
    query.GetEntityTool,
    query.FindRelationsTool,
    query.WalkPathTool,
    query.FindBottlenecksTool,
    query.FindKeyDataTool,
    query.SearchSourcesTool,
    query.ListFacetValuesTool,
    query.FulltextSearchTool,
    # Entity write (6)
    entity_write.RegisterSourceTool,
    entity_write.UpsertEntityTool,
    entity_write.SetAttributeTool,
    entity_write.AddAliasTool,
    entity_write.AddFacetValueTool,
    entity_write.DeprecateEntityTool,
    # Relation write (3)
    relation_write.UpsertRelationTool,
    relation_write.AddWeightObservationTool,
    relation_write.DeprecateRelationTool,
    # Analysis write (4)
    analysis_write.AddBottleneckTool,
    analysis_write.UpdateBottleneckTool,
    analysis_write.AddKeyDataTool,
    analysis_write.AddInvestmentThesisTool,
    # Audit + snapshot (4)
    audit_snapshot.CreateSnapshotTool,
    audit_snapshot.DiffSnapshotsTool,
    audit_snapshot.RevertToTool,
    audit_snapshot.ListRecentChangesTool,
)


def build_tools(store: IndustryGraphStore) -> list:
    """Instantiate all 25 tools bound to ``store``."""
    return [cls(store) for cls in ALL_TOOL_CLASSES]


def register_industry_graph_tools(
    store: IndustryGraphStore, registry: ToolRegistry
) -> list[str]:
    """Build and register every tool. Returns the list of registered names."""
    names = []
    for tool in build_tools(store):
        registry.register(tool)
        names.append(tool.name)
    return names


__all__ = ["ALL_TOOL_CLASSES", "build_tools", "register_industry_graph_tools"]
