from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.job_store import JobStore
from app.core.llm import LLMClient
from app.models.job import JobEvent, JobEventType
from app.tools.handlers import ToolHandlers

logger = logging.getLogger(__name__)


class AgentLoop:
    MAX_ITERATIONS = 50

    def __init__(
        self,
        job_id: str,
        query: str,
        preferences: dict[str, Any],
        job_store: JobStore,
        llm_client: LLMClient,
        tool_handlers: ToolHandlers,
        event_queue: asyncio.Queue,
    ) -> None:
        self.job_id = job_id
        self.query = query
        self.preferences = preferences
        self.job_store = job_store
        self.llm_client = llm_client
        self.tool_handlers = tool_handlers
        self.event_queue = event_queue
        self.messages: list[BaseMessage] = []

    def _load_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "prompts" / "agent.md"
        template = prompt_path.read_text(encoding="utf-8")
        prefs_text = json.dumps(self.preferences, indent=2) if self.preferences else "No specific preferences."
        return template.replace("{preferences}", prefs_text)

    async def run(self) -> None:
        logger.info("[job:%s] Starting agent loop — query=%r", self.job_id, self.query[:120])
        await self.job_store.set_running(self.job_id)

        system_prompt = self._load_system_prompt()
        self.messages.append(SystemMessage(content=system_prompt))
        self.messages.append(HumanMessage(content=self.query))

        await self.job_store.emit_event(
            self.job_id,
            JobEvent(
                event=JobEventType.MESSAGE,
                data={"role": "user", "content": self.query},
            ),
        )

        try:
            for iteration in range(self.MAX_ITERATIONS):
                logger.info(
                    "[job:%s] Iteration %d/%d — invoking LLM",
                    self.job_id, iteration + 1, self.MAX_ITERATIONS,
                )
                ai_message = await self.llm_client.invoke(self.messages)
                self.messages.append(ai_message)

                if ai_message.content:
                    await self.job_store.emit_event(
                        self.job_id,
                        JobEvent(
                            event=JobEventType.MESSAGE,
                            data={"role": "assistant", "content": ai_message.content},
                        ),
                    )

                tool_calls = LLMClient.parse_tool_calls(ai_message)
                logger.info(
                    "[job:%s] LLM response — tool_calls=%s",
                    self.job_id, [tc["name"] for tc in tool_calls] if tool_calls else "none",
                )

                if not tool_calls:
                    logger.info("[job:%s] No tool calls — marking completed.", self.job_id)
                    await self.job_store.emit_event(
                        self.job_id,
                        JobEvent(
                            event=JobEventType.COMPLETED,
                            data={"summary": ai_message.content or "Task completed."},
                        ),
                    )
                    return

                for tc in tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc["args"]
                    tool_call_id = tc["id"]

                    logger.info("[job:%s] Dispatching tool: %s", self.job_id, tool_name)
                    result = await self.tool_handlers.dispatch(
                        self.job_id, tool_name, tool_args
                    )

                    self.messages.append(
                        ToolMessage(
                            content=json.dumps(result),
                            tool_call_id=tool_call_id,
                        )
                    )

                    if tool_name == "finish_task":
                        logger.info("[job:%s] finish_task called — agent done.", self.job_id)
                        return

            logger.warning(
                "[job:%s] Max iterations (%d) reached — terminating.",
                self.job_id, self.MAX_ITERATIONS,
            )
            await self.job_store.emit_event(
                self.job_id,
                JobEvent(
                    event=JobEventType.ERROR,
                    data={"message": f"Max iterations ({self.MAX_ITERATIONS}) reached."},
                ),
            )

        except Exception as e:
            logger.exception("[job:%s] Agent loop crashed: %s", self.job_id, e)
            await self.job_store.emit_event(
                self.job_id,
                JobEvent(
                    event=JobEventType.ERROR,
                    data={"message": str(e)},
                ),
            )
