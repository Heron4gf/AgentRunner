from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.core.llm import LLMClient
from app.routers import health, jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # get_settings() raises pydantic ValidationError immediately if any .env var is missing.
    settings = get_settings()

    logger.info("=== AgentRunner starting up ===")
    logger.info("LLM model:               %s", settings.llm_model)
    logger.info("Applier model:           %s", settings.applier_model)
    logger.info("Extractor model:         %s", settings.extractor_model)
    logger.info("OpenRouter base URL:     %s", settings.openrouter_base_url)
    logger.info("Workspace root:          %s", settings.workspace_root)
    logger.info("Contexter URL:           %s", settings.contexter_url)
    logger.info("OPENROUTER_API_KEY set:  %s", bool(settings.openrouter_api_key))
    logger.info("TAVILY_API_KEY set:      %s", bool(settings.tavily_api_key))

    app.state.llm_client = LLMClient(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    )
    logger.info("LLMClient ready — startup complete.")

    yield

    # --- Shutdown ---
    logger.info("=== AgentRunner shutting down ===")


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
