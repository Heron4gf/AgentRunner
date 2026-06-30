from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.core.llm import LLMClient
from app.routers import health, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.llm_client = LLMClient(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Coding Agent Service",
        description="Cloud-native coding agent with SSE streaming, OpenRouter LLM, and Morph applier.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(jobs.router)

    return app


app = create_app()