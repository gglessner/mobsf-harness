from __future__ import annotations

import httpx


class TavilySearch:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rsp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self._key,
                "query": query,
                "max_results": limit,
                "include_answer": False,
            },
            timeout=15.0,
        )
        rsp.raise_for_status()
        data = rsp.json()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]
