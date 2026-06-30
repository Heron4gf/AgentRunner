from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openrouter import ChatOpenRouter

from app.tools.definitions import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        bind_tools: bool = True,
    ) -> None:
        # ChatOpenRouter reads OPENROUTER_API_KEY from the environment automatically.
        # No api_key or base_url argument needed.
        self.llm = ChatOpenRouter(model=model, temperature=temperature)
        self.llm_with_tools = (
            self.llm.bind_tools(TOOL_DEFINITIONS) if bind_tools else self.llm
        )
        logger.info("LLMClient initialised — model=%s bind_tools=%s", model, bind_tools)

    async def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        return await self.llm_with_tools.ainvoke(messages)

    async def invoke_plain(self, messages: list[BaseMessage]) -> AIMessage:
        """Plain invocation without tool binding — used by the extractor."""
        return await self.llm.ainvoke(messages)

    @staticmethod
    def parse_tool_calls(message: AIMessage) -> list[dict[str, Any]]:
        if not message.tool_calls:
            return []
        return [
            {"id": tc["id"], "name": tc["name"], "args": tc["args"]}
            for tc in message.tool_calls
        ]
