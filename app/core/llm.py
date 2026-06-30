from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.tools.definitions import TOOL_DEFINITIONS


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-sonnet-4.6",
        temperature: float = 0.0,
    ) -> None:
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
        )
        self.llm_with_tools = self.llm.bind_tools(TOOL_DEFINITIONS)

    async def invoke(
        self, messages: list[BaseMessage]
    ) -> AIMessage:
        return await self.llm_with_tools.ainvoke(messages)

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