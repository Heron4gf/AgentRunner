from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.models.execution import SearchMatch, SearchFilesResult


class SearchEngine:
    def __init__(self, workspace_root: str = "/workspace") -> None:
        self.workspace_root = Path(workspace_root)

    async def search(
        self,
        query: str,
        path: str | None = None,
        file_pattern: str | None = None,
        max_results: int = 50,
    ) -> SearchFilesResult:
        search_dir = self.workspace_root
        if path:
            search_dir = search_dir / path
            if not search_dir.exists():
                return SearchFilesResult(matches=[], total=0)

        cmd = [
            "rg",
            "--json",
            "--no-heading",
            "--with-filename",
            "--line-number",
            "--max-count",
            str(max_results),
        ]

        if file_pattern:
            cmd.extend(["--glob", file_pattern])

        cmd.append(query)
        cmd.append(str(search_dir))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return SearchFilesResult(matches=[], total=0)

        matches: list[SearchMatch] = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") == "match":
                data = entry.get("data", {})
                path_text = data.get("path", {}).get("text", "")
                # Make path relative to workspace
                try:
                    path_text = str(Path(path_text).relative_to(self.workspace_root))
                except ValueError:
                    pass

                lines_data = data.get("lines", {})
                line_text = lines_data.get("text", "").strip()
                line_number = data.get("line_number")

                submatch = next(iter(data.get("submatches", [])), {})
                match_text = submatch.get("match", {}).get("text", "")
                column = submatch.get("start")

                matches.append(
                    SearchMatch(
                        path=path_text,
                        line=line_number,
                        column=column,
                        match=match_text,
                        context=line_text,
                    )
                )

        # Deduplicate by (path, line) keeping first match
        seen: set[tuple[str, int]] = set()
        deduped: list[SearchMatch] = []
        for m in matches:
            key = (m.path, m.line or 0)
            if key not in seen:
                seen.add(key)
                deduped.append(m)

        return SearchFilesResult(
            matches=deduped[:max_results],
            total=len(deduped),
        )