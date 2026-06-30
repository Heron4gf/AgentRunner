from __future__ import annotations

import httpx


class ApplierClient:
    """Client for the Morph applier model via OpenRouter."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://openrouter.ai/api/v1",
        applier_model: str = "morph-v3-fast",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.applier_model = applier_model

    async def apply_edit(
        self, instruction: str, original_code: str, edit_snippet: str
    ) -> str:
        prompt = (
            f"<instruction>{instruction}</instruction>\n"
            f"<code>{original_code}</code>\n"
            f"<update>{edit_snippet}</update>"
        )

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
                                "merged final code, with no additional commentary or "
                                "markdown fences."
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

            # Strip markdown fences if the model wraps the output
            content = content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)

            return content