from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.core.job_store import JobStore
from app.core.llm import LLMClient
from app.engines.command_runner import CommandRunner
from app.engines.file_applier import FileApplier
from app.engines.search_engine import SearchEngine
from app.engines.web_search import WebSearchClient
from app.tools.handlers import ToolHandlers

# Singleton job store (shared across requests)
_job_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store


@lru_cache
def get_command_runner(settings: Settings | None = None) -> CommandRunner:
    if settings is None:
        settings = get_settings()
    return CommandRunner(workspace_root=settings.workspace_root)


@lru_cache
def get_file_applier(settings: Settings | None = None) -> FileApplier:
    if settings is None:
        settings = get_settings()
    return FileApplier(
        workspace_root=settings.workspace_root,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        applier_model=settings.applier_model,
        extractor_model=settings.extractor_model,
    )


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


@lru_cache
def get_search_engine(settings: Settings | None = None) -> SearchEngine:
    if settings is None:
        settings = get_settings()
    return SearchEngine(workspace_root=settings.workspace_root)


@lru_cache
def get_web_search_client(settings: Settings | None = None) -> WebSearchClient:
    if settings is None:
        settings = get_settings()
    return WebSearchClient(api_key=settings.tavily_api_key)


def get_tool_handlers(
    job_store: JobStore = Depends(get_job_store),
    command_runner: CommandRunner = Depends(get_command_runner),
    file_applier: FileApplier = Depends(get_file_applier),
    search_engine: SearchEngine = Depends(get_search_engine),
    web_search_client: WebSearchClient = Depends(get_web_search_client),
) -> ToolHandlers:
    return ToolHandlers(
        job_store=job_store,
        command_runner=command_runner,
        file_applier=file_applier,
        search_engine=search_engine,
        web_search_client=web_search_client,
    )
