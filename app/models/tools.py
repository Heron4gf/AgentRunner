from __future__ import annotations

from pydantic import BaseModel, Field


# ---------- run_command ----------

class RunCommandArgs(BaseModel):
    command: str
    cwd: str | None = None
    timeout: int = 30


# ---------- create_file ----------

class CreateFileArgs(BaseModel):
    path: str
    content: str


# ---------- edit_file ----------

class EditFileArgs(BaseModel):
    path: str
    instruction: str
    update: str


# ---------- delete_file ----------

class DeleteFileArgs(BaseModel):
    path: str


# ---------- search_files ----------

class SearchFilesArgs(BaseModel):
    query: str
    path: str | None = None
    file_pattern: str | None = None
    max_results: int = 50


# ---------- search_web ----------

class SearchWebArgs(BaseModel):
    query: str
    max_results: int = 5


# ---------- finish_task ----------

class FinishTaskArgs(BaseModel):
    summary: str = Field(default="Task completed")