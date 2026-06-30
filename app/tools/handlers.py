from __future__ import annotations

import uuid
from typing import Any

from app.core.job_store import JobStore
from app.engines.command_runner import CommandRunner
from app.engines.file_applier import FileApplier
from app.engines.search_engine import SearchEngine
from app.engines.web_search import WebSearchClient
from app.models.job import JobEvent, JobEventType
from app.models.tools import (
    CreateFileArgs,
    DeleteFileArgs,
    EditFileArgs,
    FinishTaskArgs,
    RunCommandArgs,
    SearchFilesArgs,
    SearchWebArgs,
)


class ToolHandlers:
    def __init__(
        self,
        job_store: JobStore,
        command_runner: CommandRunner,
        file_applier: FileApplier,
        search_engine: SearchEngine,
        web_search_client: WebSearchClient,
    ) -> None:
        self.job_store = job_store
        self.command_runner = command_runner
        self.file_applier = file_applier
        self.search_engine = search_engine
        self.web_search_client = web_search_client

    async def dispatch(
        self, job_id: str, tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        call_id = str(uuid.uuid4())

        # Emit tool_call event
        await self.job_store.emit_event(
            job_id,
            JobEvent(
                event=JobEventType.TOOL_CALL,
                call_id=call_id,
                data={"tool": tool_name, "args": args},
            ),
        )

        try:
            result = await self._execute(tool_name, args, job_id, call_id)
        except Exception as e:
            result = {"error": str(e)}

        # Emit tool_result event
        await self.job_store.emit_event(
            job_id,
            JobEvent(
                event=JobEventType.TOOL_RESULT,
                call_id=call_id,
                data={"tool": tool_name, "result": result},
            ),
        )

        return result

    async def _execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        job_id: str,
        call_id: str,
    ) -> dict[str, Any]:
        if tool_name == "run_command":
            return await self._handle_run_command(args)
        elif tool_name == "create_file":
            return await self._handle_create_file(args, job_id)
        elif tool_name == "edit_file":
            return await self._handle_edit_file(args, job_id)
        elif tool_name == "delete_file":
            return await self._handle_delete_file(args, job_id)
        elif tool_name == "search_files":
            return await self._handle_search_files(args)
        elif tool_name == "search_web":
            return await self._handle_search_web(args)
        elif tool_name == "finish_task":
            return await self._handle_finish_task(args, job_id)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    async def _handle_run_command(self, args: dict[str, Any]) -> dict[str, Any]:
        parsed = RunCommandArgs(**args)
        result = await self.command_runner.run(
            command=parsed.command,
            cwd=parsed.cwd,
            timeout=parsed.timeout,
        )
        return result.model_dump()

    async def _handle_create_file(
        self, args: dict[str, Any], job_id: str
    ) -> dict[str, Any]:
        parsed = CreateFileArgs(**args)
        result = await self.file_applier.create(
            path=parsed.path, content=parsed.content
        )
        await self.job_store.emit_event(
            job_id,
            JobEvent(
                event=JobEventType.FILE_CHANGE,
                data=result.model_dump(),
            ),
        )
        return result.model_dump()

    async def _handle_edit_file(
        self, args: dict[str, Any], job_id: str
    ) -> dict[str, Any]:
        parsed = EditFileArgs(**args)
        result = await self.file_applier.edit(
            path=parsed.path,
            instruction=parsed.instruction,
            update=parsed.update,
        )
        await self.job_store.emit_event(
            job_id,
            JobEvent(
                event=JobEventType.FILE_CHANGE,
                data=result.model_dump(),
            ),
        )
        return result.model_dump()

    async def _handle_delete_file(
        self, args: dict[str, Any], job_id: str
    ) -> dict[str, Any]:
        parsed = DeleteFileArgs(**args)
        result = await self.file_applier.delete(path=parsed.path)
        await self.job_store.emit_event(
            job_id,
            JobEvent(
                event=JobEventType.FILE_CHANGE,
                data=result.model_dump(),
            ),
        )
        return result.model_dump()

    async def _handle_search_files(self, args: dict[str, Any]) -> dict[str, Any]:
        parsed = SearchFilesArgs(**args)
        result = await self.search_engine.search(
            query=parsed.query,
            path=parsed.path,
            file_pattern=parsed.file_pattern,
            max_results=parsed.max_results,
        )
        return result.model_dump()

    async def _handle_search_web(self, args: dict[str, Any]) -> dict[str, Any]:
        parsed = SearchWebArgs(**args)
        result = await self.web_search_client.search(
            query=parsed.query, max_results=parsed.max_results
        )
        return result.model_dump()

    async def _handle_finish_task(
        self, args: dict[str, Any], job_id: str
    ) -> dict[str, Any]:
        parsed = FinishTaskArgs(**args)
        await self.job_store.emit_event(
            job_id,
            JobEvent(
                event=JobEventType.COMPLETED,
                data={"summary": parsed.summary},
            ),
        )
        return {"status": "completed", "summary": parsed.summary}