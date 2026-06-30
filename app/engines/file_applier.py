from __future__ import annotations

import difflib
from pathlib import Path

import httpx

from app.models.execution import FileChangeResult


class FileApplier:
    def __init__(
        self,
        workspace_root: str = "/workspace",
        api_key: str = "",
        base_url: str = "https://openrouter.ai/api/v1",
        applier_model: str = "morph/morph-v3-fast",
        extractor_model: str = "qwen/Qwen-3.6-flash",
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
        return FileChangeResult(operation="create", path=path, diff=diff)

    async def edit(
        self,
        path: str,
        instruction: str,
        update: str,
        file_content: str,
    ) -> FileChangeResult:
        # Step 1: Extract relevant methods using small LLM
        extracted = await self._extract_context(
            path=path,
            instruction=instruction,
            file_content=file_content,
        )

        # Step 2: Call Morph applier on extracted section only
        morph_prompt = (
            f"<instruction>{instruction}</instruction>\n"
            f"<code>{extracted}</code>\n"
            f"<update>{update}</update>"
        )
        merged_section = await self._call_applier(morph_prompt)

        # Step 3: Reconstruct full file — replace extracted section with merged
        if extracted and extracted in file_content:
            updated_content = file_content.replace(extracted, merged_section, 1)
        else:
            # Fallback: feed full file to Morph if extraction doesn't match verbatim
            full_prompt = (
                f"<instruction>{instruction}</instruction>\n"
                f"<code>{file_content}</code>\n"
                f"<update>{update}</update>"
            )
            updated_content = await self._call_applier(full_prompt)

        # Write to disk (for workspace persistence) and compute diff
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(updated_content, encoding="utf-8")

        diff = self._compute_diff(file_content, updated_content, path)
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
        # Direct httpx call to OpenRouter — same pattern as _call_applier
        # Uses self.extractor_model, temperature=0, no system prompt needed
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
                            "content": "You are a code editor. Apply the given edit instruction and update snippet to the provided code. Output ONLY the merged final code, with no additional commentary or markdown fences.",
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

            # Strip markdown fences if the model wraps the output
            content = content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)

            return content