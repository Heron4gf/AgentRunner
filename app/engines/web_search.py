from __future__ import annotations

import logging

from tavily import AsyncTavilyClient

from app.models.execution import SearchWebResult, WebSearchResultItem

logger = logging.getLogger(__name__)


class WebSearchClient:
    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self._client: AsyncTavilyClient | None = None

    def _get_client(self) -> AsyncTavilyClient:
        if self._client is None:
            self._client = AsyncTavilyClient(api_key=self.api_key)
        return self._client

    async def search(self, query: str, max_results: int = 5) -> SearchWebResult:
        logger.info("Tavily search — query=%r max_results=%d", query, max_results)
        client = self._get_client()
        response = await client.search(query=query, max_results=max_results)

        results: list[WebSearchResultItem] = [
            WebSearchResultItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=item.get("score"),
            )
            for item in response.get("results", [])
        ]
        logger.info("Tavily returned %d results", len(results))
        return SearchWebResult(results=results, total=len(results))
