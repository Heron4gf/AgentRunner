from __future__ import annotations

import difflib
import logging
from pathlib import Path

import httpx

from app.models.execution import FileChangeResult

logger = logging.getLogger(__name__)


class FileApplier:
    def __init__(
        self,
        workspace_root: str = "/workspace",
        api_key: str = "",
        base_url: str = "https://openrouter.ai/api/v1",
        applier_model: str = "morph/morph-v3-fast",
        extractor_model: str = "qwen/qwen3-8b",
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.applier_model = applier_model
        self.extractor_model = extractor_model

    def _resolve_path(self, path: str) -> Path:
        resolved = (self.workspace_root / path).resolve()
        if not str(resolved).startswith(str(self.workspace_root.resolve())):
            raise ValueError(f"Path {path} is outside workspace root")
        return resolved

    def _compute_diff(self, original: str, updated: str, path: str) -> str:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        return "".join(diff)

    async def create(self, path: str, content: str) -> FileChangeResult:
        file_path = self._resolve_path(path)
        if file_path.exists():
            raise FileExistsError(f"File {path} already exists")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        diff = self._compute_diff("", content, path)
        logger.info("Created file: %s", path)
        return FileChangeResult(operation="create", path=path, diff=diff)

    async def edit(
        self,
        path: str,
        instruction: str,
        update: str,
        file_content: str,
    ) -> FileChangeResult:
        # Step 1: Extract relevant methods/classes using the small extractor LLM
        logger.info("[edit:%s] Step 1 — extracting context (model=%s)", path, self.extractor_model)
        extracted = await self._extract_context(
            path=path,
            instruction=instruction,
            file_content=file_content,
        )

        # Step 2: Call Morph applier on the extracted section only
        logger.info("[edit:%s] Step 2 — calling Morph applier (model=%s)", path, self.applier_model)
        morph_prompt = (
            f"<instruction>{instruction}</instruction>\n"
            f"<code>{extracted}</code>\n"
            f"<update>{update}</update>"
        )
        merged_section = await self._call_applier(morph_prompt)

        # Step 3: Reconstruct the full file by replacing the extracted section
        if extracted and extracted in file_content:
            updated_content = file_content.replace(extracted, merged_section, 1)
        else:
            # Fallback: verbatim match failed — feed full file to Morph directly
            logger.warning(
                "[edit:%s] Verbatim extraction match failed — falling back to full-file applier", path
            )
            full_prompt = (
                f"<instruction>{instruction}</instruction>\n"
                f"<code>{file_content}</code>\n"
                f"<update>{update}</update>"
            )
            updated_content = await self._call_applier(full_prompt)

        # Write result to workspace disk and compute diff
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(updated_content, encoding="utf-8")

        diff = self._compute_diff(file_content, updated_content, path)
        logger.info("[edit:%s] Edit complete — %d lines changed", path, diff.count("\n"))
        return FileChangeResult(
            operation="edit",
            path=path,
            diff=diff,
            original_content=file_content,
            updated_content=updated_content,
        )

    async def delete(self, path: str) -> FileChangeResult:
        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File {path} not found")
        original_content = file_path.read_text(encoding="utf-8")
        file_path.unlink()
        diff = self._compute_diff(original_content, "", path)
        logger.info("Deleted file: %s", path)
        return FileChangeResult(
            operation="delete",
            path=path,
            diff=diff,
            original_content=original_content,
        )

    async def _extract_context(
        self, path: str, instruction: str, file_content: str
    ) -> str:
        prompt_template = (
            Path(__file__).parent.parent / "prompts" / "extractor.md"
        ).read_text(encoding="utf-8")
        prompt = (
            prompt_template
            .replace("{instruction}", instruction)
            .replace("{path}", path)
            .replace("{file_content}", file_content)
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.extractor_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 4096,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()

    async def _call_applier(self, prompt: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.applier_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a code editor. Apply the given edit instruction "
                                "and update snippet to the provided code. Output ONLY the "
                                "merged final code, with no additional commentary or markdown fences."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 8192,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            content = content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)

            return content
