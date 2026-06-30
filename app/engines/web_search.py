from __future__ import annotations

from app.models.execution import SearchWebResult, WebSearchResultItem


class WebSearchClient:
    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    async def search(self, query: str, max_results: int = 5) -> SearchWebResult:
        client = self._get_client()
        response = client.search(query=query, max_results=max_results)

        results: list[WebSearchResultItem] = []
        for item in response.get("results", []):
            results.append(
                WebSearchResultItem(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    score=item.get("score"),
                )
            )

        return SearchWebResult(results=results, total=len(results))