from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.tools.definitions import TOOL_DEFINITIONS


class LLMClient:
    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4.6",
        temperature: float = 0.0,
        bind_tools: bool = True,
    ) -> None:
        settings = get_settings()
        self.llm = ChatOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=model,
            temperature=temperature,
        )
        self.llm_with_tools = (
            self.llm.bind_tools(TOOL_DEFINITIONS) if bind_tools else self.llm
        )

    async def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        return await self.llm_with_tools.ainvoke(messages)

    async def invoke_plain(self, messages: list[BaseMessage]) -> AIMessage:
        """For the extractor — no tool binding."""
        return await self.llm.ainvoke(messages)

    @staticmethod
    def parse_tool_calls(message: AIMessage) -> list[dict[str, Any]]:
        if not message.tool_calls:
            return []
        return [
            {
                "id": tc["id"],
                "name": tc["name"],
                "args": tc["args"],
            }
            for tc in message.tool_calls
        ]