from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.job_store import JobStore
from app.core.llm import LLMClient
from app.models.job import JobEvent, JobEventType
from app.tools.handlers import ToolHandlers


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
        await self.job_store.set_running(self.job_id)

        system_prompt = self._load_system_prompt()
        self.messages.append(SystemMessage(content=system_prompt))
        self.messages.append(HumanMessage(content=self.query))

        # Emit message event for the initial query
        await self.job_store.emit_event(
            self.job_id,
            JobEvent(
                event=JobEventType.MESSAGE,
                data={"role": "user", "content": self.query},
            ),
        )

        try:
            for _ in range(self.MAX_ITERATIONS):
                ai_message = await self.llm_client.invoke(self.messages)
                self.messages.append(ai_message)

                # Emit assistant message
                if ai_message.content:
                    await self.job_store.emit_event(
                        self.job_id,
                        JobEvent(
                            event=JobEventType.MESSAGE,
                            data={"role": "assistant", "content": ai_message.content},
                        ),
                    )

                tool_calls = LLMClient.parse_tool_calls(ai_message)

                if not tool_calls:
                    # No tool calls and no finish_task: treat as completion
                    await self.job_store.emit_event(
                        self.job_id,
                        JobEvent(
                            event=JobEventType.COMPLETED,
                            data={"summary": ai_message.content or "Task completed."},
                        ),
                    )
                    return

                # Execute each tool call
                for tc in tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc["args"]
                    tool_call_id = tc["id"]

                    result = await self.tool_handlers.dispatch(
                        self.job_id, tool_name, tool_args
                    )

                    # Add tool result to message history
                    self.messages.append(
                        ToolMessage(
                            content=json.dumps(result),
                            tool_call_id=tool_call_id,
                        )
                    )

                    # Check for finish_task
                    if tool_name == "finish_task":
                        return

            # Max iterations reached
            await self.job_store.emit_event(
                self.job_id,
                JobEvent(
                    event=JobEventType.ERROR,
                    data={"message": f"Max iterations ({self.MAX_ITERATIONS}) reached."},
                ),
            )

        except Exception as e:
            await self.job_store.emit_event(
                self.job_id,
                JobEvent(
                    event=JobEventType.ERROR,
                    data={"message": str(e)},
                ),
            )