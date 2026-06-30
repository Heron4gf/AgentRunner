from fastapi import FastAPI

from app.routers import health, jobs


def create_app() -> FastAPI:
    app = FastAPI(
        title="Coding Agent Service",
        description="Cloud-native coding agent with SSE streaming, OpenRouter LLM, and Morph applier.",
        version="0.1.0",
    )

    app.include_router(health.router)
    app.include_router(jobs.router)

    return app


app = create_app()