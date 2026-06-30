from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_job_store, get_tool_handlers
from app.config import get_settings
from app.core.agent import AgentLoop
from app.core.job_store import JobStore
from app.core.llm import LLMClient
from app.models.job import (
    CreateJobRequest,
    JobEvent,
    JobEventType,
    JobRecord,
    JobResponse,
    JobStatus,
    JobStatusResponse,
)
from app.tools.handlers import ToolHandlers

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: CreateJobRequest,
    job_store: JobStore = Depends(get_job_store),
    tool_handlers: ToolHandlers = Depends(get_tool_handlers),
) -> JobResponse:
    settings = get_settings()

    # Call Contexter to get preferences
    from app.clients.contexter import ContexterClient

    contexter = ContexterClient(base_url=settings.contexter_url)
    try:
        contexter_task = await contexter.create_task(
            query=body.query, project_id=body.project_id
        )
        task_id = contexter_task.id
        preferences = contexter_task.preferences
    except Exception:
        # Contexter unavailable: proceed without preferences
        task_id = None
        preferences = {}

    record = JobRecord(
        query=body.query,
        task_id=task_id,
        project_id=body.project_id,
        preferences=preferences,
        status=JobStatus.QUEUED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    job_record, event_queue = job_store.create_job(record)

    # Launch agent loop as background task
    llm_client = LLMClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    )
    agent = AgentLoop(
        job_id=job_record.job_id,
        query=body.query,
        preferences=preferences,
        job_store=job_store,
        llm_client=llm_client,
        tool_handlers=tool_handlers,
        event_queue=event_queue,
    )
    asyncio.create_task(agent.run())

    return JobResponse(
        job_id=job_record.job_id,
        task_id=job_record.task_id or "",
        status=JobStatus.QUEUED,
    )


@router.get("/{job_id}/events")
async def stream_events(
    job_id: str,
    request: Request,
    job_store: JobStore = Depends(get_job_store),
) -> EventSourceResponse:
    try:
        queue = job_store.get_event_queue(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                event: JobEvent = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield {"comment": "keepalive"}
                continue

            yield {
                "event": event.event.value,
                "data": event.model_dump_json(),
            }

            if event.event in (
                JobEventType.COMPLETED,
                JobEventType.CANCELLED,
                JobEventType.ERROR,
            ):
                break

    return EventSourceResponse(event_generator())


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: str,
    job_store: JobStore = Depends(get_job_store),
) -> JobStatusResponse:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job.job_id,
        task_id=job.task_id,
        status=job.status,
        query=job.query,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
    )


@router.get("", response_model=list[JobStatusResponse])
async def list_jobs(
    skip: int = 0,
    limit: int = 100,
    job_store: JobStore = Depends(get_job_store),
) -> list[JobStatusResponse]:
    jobs = job_store.list_jobs(skip=skip, limit=limit)
    return [
        JobStatusResponse(
            job_id=j.job_id,
            task_id=j.task_id,
            status=j.status,
            query=j.query,
            created_at=j.created_at,
            updated_at=j.updated_at,
            error=j.error,
        )
        for j in jobs
    ]


@router.post("/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_job(
    job_id: str,
    job_store: JobStore = Depends(get_job_store),
) -> JobStatusResponse:
    job = job_store.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Emit cancelled event
    await job_store.emit_event(
        job_id,
        JobEvent(event=JobEventType.CANCELLED, data={"message": "Job cancelled by user"}),
    )

    return JobStatusResponse(
        job_id=job.job_id,
        task_id=job.task_id,
        status=job.status,
        query=job.query,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
    )


@router.post("/{job_id}/input", response_model=JobStatusResponse)
async def send_input(
    job_id: str,
    body: dict,
    job_store: JobStore = Depends(get_job_store),
) -> JobStatusResponse:
    message = body.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.WAITING_INPUT:
        raise HTTPException(status_code=409, detail="Job is not waiting for input")

    # Push user message as an event and set back to running
    await job_store.emit_event(
        job_id,
        JobEvent(event=JobEventType.MESSAGE, data={"message": message}),
    )
    await job_store.set_running(job_id)

    job = job_store.get_job(job_id)
    return JobStatusResponse(
        job_id=job.job_id,
        task_id=job.task_id,
        status=job.status,
        query=job.query,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
    )