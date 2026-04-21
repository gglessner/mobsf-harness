from __future__ import annotations

import httpx


class BraveSearch:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rsp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": str(limit)},
            headers={"X-Subscription-Token": self._key, "Accept": "application/json"},
            timeout=15.0,
        )
        rsp.raise_for_status()
        data = rsp.json()
        hits = (data.get("web", {}) or {}).get("results", [])
        return [
            {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("description", "")}
            for h in hits
        ]
