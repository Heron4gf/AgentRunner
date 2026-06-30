from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.core.job_store import JobStore
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
    )


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
    job_store: JobStore | None = None,
    command_runner: CommandRunner | None = None,
    file_applier: FileApplier | None = None,
    search_engine: SearchEngine | None = None,
    web_search_client: WebSearchClient | None = None,
) -> ToolHandlers:
    settings = get_settings()
    if job_store is None:
        job_store = get_job_store()
    if command_runner is None:
        command_runner = get_command_runner(settings)
    if file_applier is None:
        file_applier = get_file_applier(settings)
    if search_engine is None:
        search_engine = get_search_engine(settings)
    if web_search_client is None:
        web_search_client = get_web_search_client(settings)
    return ToolHandlers(
        job_store=job_store,
        command_runner=command_runner,
        file_applier=file_applier,
        search_engine=search_engine,
        web_search_client=web_search_client,
    )