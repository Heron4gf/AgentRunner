from __future__ import annotations

from typing import Any

from app.tools.handlers import ToolHandlers


class ToolExecutor:
    """Thin dispatcher that delegates to ToolHandlers.

    Kept as a separate class to maintain the architectural separation
    between the agent loop (orchestration) and tool execution (dispatch).
    """

    def __init__(self, tool_handlers: ToolHandlers) -> None:
        self.tool_handlers = tool_handlers

    async def execute(
        self, job_id: str, tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.tool_handlers.dispatch(job_id, tool_name, args)