from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shinkai_api.api import a2a, auth, checkpoints, evals, graph, health, research, runs
from shinkai_api.core.config import settings
from shinkai_api.runs.executor import default_run_executor


def create_app() -> FastAPI:
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
    app.include_router(evals.router, prefix="/api/v1")
    app.include_router(a2a.router, prefix="/api/v1")

    @app.on_event("startup")
    async def recover_active_runs() -> None:
        await default_run_executor.recover_active_runs()

    return app


app = create_app()
