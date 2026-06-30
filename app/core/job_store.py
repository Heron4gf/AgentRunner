from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.models.job import JobEvent, JobEventType, JobRecord, JobStatus


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._event_queues: dict[str, asyncio.Queue[JobEvent]] = {}

    def create_job(self, record: JobRecord) -> tuple[JobRecord, asyncio.Queue[JobEvent]]:
        self._jobs[record.job_id] = record
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        self._event_queues[record.job_id] = queue
        return record, queue

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def get_event_queue(self, job_id: str) -> asyncio.Queue[JobEvent]:
        queue = self._event_queues.get(job_id)
        if queue is None:
            raise KeyError(f"No event queue for job {job_id}")
        return queue

    async def emit_event(self, job_id: str, event: JobEvent) -> None:
        """Push an event onto the job's SSE queue."""
        queue = self._event_queues.get(job_id)
        if queue is not None:
            await queue.put(event)
        # Update status based on terminal events
        if event.event in (JobEventType.COMPLETED, JobEventType.CANCELLED):
            self._update_status(
                job_id,
                JobStatus.COMPLETED if event.event == JobEventType.COMPLETED else JobStatus.CANCELLED,
            )
        elif event.event == JobEventType.ERROR:
            self._update_status(job_id, JobStatus.FAILED, error=str(event.data.get("message", "")))

    def _update_status(self, job_id: str, status: JobStatus, error: str | None = None) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = status
            job.updated_at = datetime.now(timezone.utc)
            if error:
                job.error = error

    def list_jobs(self, skip: int = 0, limit: int = 100) -> list[JobRecord]:
        jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[skip : skip + limit]

    def cancel_job(self, job_id: str) -> JobRecord | None:
        job = self._jobs.get(job_id)
        if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.WAITING_INPUT):
            job.status = JobStatus.CANCELLED
            job.updated_at = datetime.now(timezone.utc)
        return job

    async def set_waiting_input(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.WAITING_INPUT
            job.updated_at = datetime.now(timezone.utc)

    async def set_running(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.updated_at = datetime.now(timezone.utc)