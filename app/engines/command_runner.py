from __future__ import annotations

import subprocess
import time
from pathlib import Path

from app.models.execution import RunCommandResult


class CommandRunner:
    def __init__(self, workspace_root: str = "/workspace") -> None:
        self.workspace_root = Path(workspace_root)

    async def run(
        self, command: str, cwd: str | None = None, timeout: int = 30
    ) -> RunCommandResult:
        working_dir = str(self.workspace_root / cwd) if cwd else str(self.workspace_root)
        start = time.monotonic()

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return RunCommandResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return RunCommandResult(
                stdout=e.stdout or "",
                stderr=e.stderr or f"Command timed out after {timeout}s",
                exit_code=-1,
                duration_ms=duration_ms,
            )