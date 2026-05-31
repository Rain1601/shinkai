from __future__ import annotations

import pytest

from shinkai_api.llm import LLMRouter


class _StubBackend:
    def __init__(self, name: str) -> None:
        self.name = name

    async def chat_json(self, *, system, user, temperature=0.2, max_tokens=1800):
        return {"system": system, "user": user, "_backend": self.name}


def test_router_routes_task_to_registered_backend() -> None:
    router = LLMRouter()
    router.register_backend(_StubBackend("deepseek-chat"))
    router.register_backend(_StubBackend("claude-via-aihubmix"))

    router.set_route("planner", "deepseek-chat", "cheap and structured")
    router.set_route("critic", "claude-via-aihubmix", "deep reasoning")

    assert router.get_backend_for("planner").name == "deepseek-chat"
    assert router.get_backend_for("critic").name == "claude-via-aihubmix"
    assert {route.task_type for route in router.list_routes()} == {"planner", "critic"}
    assert set(router.list_backends()) == {"deepseek-chat", "claude-via-aihubmix"}


def test_router_raises_for_unknown_task() -> None:
    router = LLMRouter()
    router.register_backend(_StubBackend("deepseek-chat"))

    with pytest.raises(KeyError):
        router.get_backend_for("nonexistent_task")


def test_router_raises_for_unregistered_backend() -> None:
    router = LLMRouter()

    with pytest.raises(KeyError):
        router.set_route("planner", "claude-via-aihubmix")
