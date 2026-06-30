from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # All fields are required — no Python-level defaults.
    # Every value must be present in .env (or as an environment variable).
    # If anything is missing, pydantic_settings raises a ValidationError at startup.
    openrouter_api_key: str
    tavily_api_key: str
    contexter_url: str
    workspace_root: str
    llm_model: str
    applier_model: str
    extractor_model: str
    llm_temperature: float
    openrouter_base_url: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
