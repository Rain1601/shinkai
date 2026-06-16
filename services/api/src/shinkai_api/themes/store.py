from __future__ import annotations

from shinkai_api.core.async_lock import LoopBoundLock
from shinkai_api.persistence import default_state_store
from shinkai_api.themes.models import ThemeGraph, empty_graph


class ThemeGraphStore:
    """Singleton store for the theme graph.

    One graph at a time, persisted under the ``theme_graph`` section of the
    state store. Rebuilds replace the whole document; there is no diff path.
    """

    SECTION = "theme_graph"

    def __init__(self) -> None:
        self._graph: ThemeGraph | None = None
        self._lock = LoopBoundLock()
        self._loaded = False

    async def get(self) -> ThemeGraph:
        async with self._lock.get():
            await self._ensure_loaded()
            assert self._graph is not None
            return self._graph

    async def set(self, graph: ThemeGraph) -> ThemeGraph:
        async with self._lock.get():
            self._graph = graph
            self._loaded = True
            await default_state_store.save_section(
                self.SECTION,
                graph.model_dump(mode="json"),
            )
            return graph

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        state = await default_state_store.load()
        payload = state.get(self.SECTION)
        if isinstance(payload, dict):
            try:
                self._graph = ThemeGraph.model_validate(payload)
            except Exception:
                self._graph = empty_graph()
        else:
            self._graph = empty_graph()
        self._loaded = True

    def _reset_for_tests(self) -> None:
        self._graph = None
        self._loaded = False


default_theme_graph_store = ThemeGraphStore()
