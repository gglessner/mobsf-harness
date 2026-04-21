import httpx
import pytest
import respx

from mobsf_harness.config import WebSearchConfig
from mobsf_harness.tools.search import make_web_search
from mobsf_harness.tools.search.tavily import TavilySearch
from mobsf_harness.tools.search.brave import BraveSearch


@respx.mock
def test_tavily_returns_results():
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "T", "url": "u", "content": "snippet"}]},
        )
    )
    hits = TavilySearch(api_key="k").search("cve-2024", limit=3)
    assert hits == [{"title": "T", "url": "u", "snippet": "snippet"}]


@respx.mock
def test_brave_returns_results():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            json={"web": {"results": [{"title": "T2", "url": "u2", "description": "d"}]}},
        )
    )
    hits = BraveSearch(api_key="k").search("cve-2024", limit=3)
    assert hits == [{"title": "T2", "url": "u2", "snippet": "d"}]


def test_factory_picks_duckduckgo_without_api_key():
    cfg = WebSearchConfig(backend="duckduckgo")
    impl = make_web_search(cfg)
    assert type(impl).__name__ == "DuckDuckGoSearch"
