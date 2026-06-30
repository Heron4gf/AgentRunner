from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobEventType(str, Enum):
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FILE_CHANGE = "file_change"
    ERROR = "error"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CreateJobRequest(BaseModel):
    query: str
    project_id: str | None = None
    workspace_id: str | None = None


class JobResponse(BaseModel):
    job_id: str
    task_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    task_id: str | None = None
    status: JobStatus
    query: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class JobEvent(BaseModel):
    event: JobEventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    call_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str | None = None
    status: JobStatus = JobStatus.QUEUED
    query: str
    preferences: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error: str | None = None