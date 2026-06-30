from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field


class ContexterTask(BaseModel):
    id: str
    project_id: str | None = None
    query: str
    preferences: dict[str, Any] = Field(default_factory=dict)


class ContexterClient:
    def __init__(self, base_url: str = "http://localhost:8001") -> None:
        self.base_url = base_url.rstrip("/")

    async def create_task(
        self, query: str, project_id: str | None = None
    ) -> ContexterTask:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/tasks",
                json={"query": query, "projectId": project_id},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return ContexterTask(
                id=data["id"],
                project_id=data.get("projectId"),
                query=data["query"],
                preferences=data.get("preferences", {}),
            )