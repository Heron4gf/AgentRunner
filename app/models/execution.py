from __future__ import annotations

from pydantic import BaseModel


class RunCommandResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class SearchMatch(BaseModel):
    path: str
    line: int | None = None
    column: int | None = None
    match: str
    context: str | None = None


class SearchFilesResult(BaseModel):
    matches: list[SearchMatch]
    total: int


class WebSearchResultItem(BaseModel):
    title: str
    url: str
    content: str
    score: float | None = None


class SearchWebResult(BaseModel):
    results: list[WebSearchResultItem]
    total: int


class FileChangeResult(BaseModel):
    operation: str  # "create" | "edit" | "delete"
    path: str
    diff: str
    original_content: str | None = None
    updated_content: str | None = None