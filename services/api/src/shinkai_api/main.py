import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shinkai_api.api import (
    a2a,
    actions,
    agent,
    auth,
    checkpoints,
    evals,
    graph,
    health,
    research,
    results,
    runs,
    themes,
)
from shinkai_api.core.config import settings
from shinkai_api.runs.executor import default_run_executor


def _bridge_env_to_market_utils() -> None:
    """Mirror SHINKAI_-prefixed search keys to the names market-utils expects.

    market-utils reads ``TAVILY_API_KEY`` / ``GOOGLE_SEARCH_API_KEY`` etc.
    directly from os.environ. shinkai loads its config via pydantic-settings
    with the ``SHINKAI_`` prefix. Bridge them once at boot so the package
    can find keys without us re-implementing settings loading.
    """
    if settings.tavily_api_key and not os.environ.get("TAVILY_API_KEY"):
        os.environ["TAVILY_API_KEY"] = settings.tavily_api_key
    if settings.tavily_base_url:
        os.environ.setdefault("TAVILY_BASE_URL", settings.tavily_base_url)

    google_key = getattr(settings, "google_search_api_key", None) or os.environ.get(
        "SHINKAI_GOOGLE_SEARCH_API_KEY"
    )
    google_cx = getattr(settings, "google_search_engine_id", None) or os.environ.get(
        "SHINKAI_GOOGLE_SEARCH_ENGINE_ID"
    )
    if google_key and not os.environ.get("GOOGLE_SEARCH_API_KEY"):
        os.environ["GOOGLE_SEARCH_API_KEY"] = google_key
    if google_cx and not os.environ.get("GOOGLE_SEARCH_ENGINE_ID"):
        os.environ["GOOGLE_SEARCH_ENGINE_ID"] = google_cx


def create_app() -> FastAPI:
    _bridge_env_to_market_utils()
    app = FastAPI(
        title="Shinkai API",
        version="1.0.0",
        description="Long-running investment research agent API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(checkpoints.router, prefix="/api/v1")
    app.include_router(graph.router, prefix="/api/v1")
    app.include_router(research.router, prefix="/api/v1")
    app.include_router(results.router, prefix="/api/v1")
    app.include_router(results.run_result_router, prefix="/api/v1")
    app.include_router(evals.router, prefix="/api/v1")
    app.include_router(a2a.router, prefix="/api/v1")
    app.include_router(themes.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    app.include_router(actions.router, prefix="/api/v1")

    @app.on_event("startup")
    async def recover_active_runs() -> None:
        await default_run_executor.recover_active_runs()

    return app


app = create_app()
