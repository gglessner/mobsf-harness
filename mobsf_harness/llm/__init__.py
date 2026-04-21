from __future__ import annotations

from mobsf_harness.config import LlmConfig

from .anthropic_client import AnthropicClient
from .openai_client import OpenAICompatibleClient
from .types import LlmClient, LlmResponse, Message, ToolCall, ToolResult, ToolSchema


def make_client(cfg: LlmConfig) -> LlmClient:
    if cfg.provider == "anthropic":
        return AnthropicClient(api_key=cfg.api_key)
    if cfg.provider == "openai-compatible":
        return OpenAICompatibleClient(api_key=cfg.api_key, base_url=cfg.base_url or "")
    raise ValueError(f"unknown llm provider: {cfg.provider}")


__all__ = [
    "AnthropicClient",
    "LlmClient",
    "LlmResponse",
    "Message",
    "OpenAICompatibleClient",
    "ToolCall",
    "ToolResult",
    "ToolSchema",
    "make_client",
]
