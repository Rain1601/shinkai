"""LLMRouter — single dispatch point for multi-provider LLM calls.

Per alignment-v2, shinkai routes work between DeepSeek (workhorse) and Claude via
AIHubMix (hard reasoning). Today only DeepSeek is wired through the harness; this
router introduces the abstraction so that adding a Claude/AIHubMix backend later
is a single registration call rather than a harness edit.

Routing key examples:
    "planner"          -> DeepSeek (cheap, structured frontier proposal)
    "critic"           -> Claude (deep evidence weighing) — not built yet
    "report_writer"    -> DeepSeek (long-form, no hard reasoning)

The router intentionally does NOT auto-fail-over between providers; that would
mask cost/quality drift. Callers ask for a specific task type and get the
provider mapped to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMBackend(Protocol):
    name: str

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1800,
    ) -> dict[str, Any]: ...


@dataclass
class TaskRoute:
    task_type: str
    backend_name: str
    rationale: str = ""


class LLMRouter:
    def __init__(self) -> None:
        self._backends: dict[str, LLMBackend] = {}
        self._routes: dict[str, TaskRoute] = {}

    def register_backend(self, backend: LLMBackend) -> None:
        self._backends[backend.name] = backend

    def set_route(self, task_type: str, backend_name: str, rationale: str = "") -> None:
        if backend_name not in self._backends:
            raise KeyError(f"backend not registered: {backend_name}")
        self._routes[task_type] = TaskRoute(task_type, backend_name, rationale)

    def get_backend_for(self, task_type: str) -> LLMBackend:
        route = self._routes.get(task_type)
        if route is None:
            raise KeyError(f"no route registered for task: {task_type}")
        return self._backends[route.backend_name]

    def list_routes(self) -> list[TaskRoute]:
        return list(self._routes.values())

    def list_backends(self) -> list[str]:
        return list(self._backends.keys())


default_llm_router = LLMRouter()
