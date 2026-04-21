from __future__ import annotations

import re
from html import unescape

import httpx


_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def _strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


class DuckDuckGoSearch:
    def __init__(self) -> None:
        pass

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rsp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            timeout=15.0,
            headers={"User-Agent": "mobsf-harness/0.1 (+https://example.invalid)"},
        )
        rsp.raise_for_status()
        hits: list[dict] = []
        for m in _RESULT_RE.finditer(rsp.text):
            hits.append(
                {
                    "url": m.group(1),
                    "title": _strip_tags(m.group(2)),
                    "snippet": _strip_tags(m.group(3)),
                }
            )
            if len(hits) >= limit:
                break
        return hits
