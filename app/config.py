from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    openrouter_api_key: str
    tavily_api_key: str
    contexter_url: str = "http://localhost:8001"
    workspace_root: str = "/workspace"
    llm_model: str = "anthropic/claude-sonnet-4.6"
    applier_model: str = "morph-v3-fast"
    llm_temperature: float = 0.0
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()