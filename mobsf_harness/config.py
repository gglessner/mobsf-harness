from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


class ConfigError(Exception):
    """Raised when the harness config is invalid or missing required values."""


class MobsfConfig(BaseModel):
    url: str
    api_key_env: str
    api_key: str = ""

    @model_validator(mode="after")
    def _resolve_key(self) -> "MobsfConfig":
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(f"env var {self.api_key_env} is not set")
        self.api_key = key
        return self


class LlmConfig(BaseModel):
    provider: Literal["anthropic", "openai-compatible"]
    model: str
    base_url: str | None = None
    api_key_env: str
    api_key: str = ""
    max_turns: int = 12
    max_tokens_per_session: int = 100_000

    @model_validator(mode="after")
    def _validate(self) -> "LlmConfig":
        if self.provider == "openai-compatible" and not self.base_url:
            raise ValueError("llm.base_url is required when provider is openai-compatible")
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(f"env var {self.api_key_env} is not set")
        self.api_key = key
        return self


class WebSearchConfig(BaseModel):
    backend: Literal["tavily", "brave", "duckduckgo"]
    api_key_env: str | None = None
    api_key: str = ""

    @model_validator(mode="after")
    def _resolve(self) -> "WebSearchConfig":
        if self.backend == "duckduckgo":
            return self
        if not self.api_key_env:
            raise ValueError(f"web_search.api_key_env is required for backend {self.backend}")
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError(f"env var {self.api_key_env} is not set")
        self.api_key = key
        return self


class LogChannel(BaseModel):
    path: str


class EmailChannel(BaseModel):
    smtp_host: str
    smtp_port: int
    from_addr: str
    to_addrs: list[str]
    username_env: str | None = None
    password_env: str | None = None
    username: str = ""
    password: str = ""

    @model_validator(mode="after")
    def _resolve(self) -> "EmailChannel":
        if self.username_env:
            self.username = os.environ.get(self.username_env, "")
        if self.password_env:
            self.password = os.environ.get(self.password_env, "")
        return self


class WebhookChannel(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class NotificationsConfig(BaseModel):
    log: LogChannel | None = None
    email: EmailChannel | None = None
    webhook: WebhookChannel | None = None


class Defaults(BaseModel):
    dynamic_analysis: bool = False
    notification_channels: list[str] = Field(default_factory=lambda: ["log"])


class AppEntry(BaseModel):
    platform: Literal["android", "ios"]
    package_id: str | None = None
    bundle_id: str | None = None
    source: Literal["play_store", "app_store", "drop_dir"]
    notification_channels: list[str] | None = None
    dynamic_analysis: bool | None = None
    tags: list[str] = Field(default_factory=list)
    drop_path: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "AppEntry":
        if self.platform == "android" and not self.package_id:
            raise ValueError("android app requires package_id")
        if self.platform == "ios" and not self.bundle_id:
            raise ValueError("ios app requires bundle_id")
        if self.source == "drop_dir" and not self.drop_path:
            raise ValueError("drop_dir source requires drop_path")
        return self

    @property
    def identifier(self) -> str:
        return self.package_id or self.bundle_id  # type: ignore[return-value]


class Config(BaseModel):
    defaults: Defaults = Field(default_factory=Defaults)
    mobsf: MobsfConfig
    llm: LlmConfig
    web_search: WebSearchConfig
    notifications: NotificationsConfig
    policy: str = ""
    apps: list[AppEntry]

    @model_validator(mode="after")
    def _apply_defaults(self) -> "Config":
        for app in self.apps:
            if app.notification_channels is None:
                app.notification_channels = list(self.defaults.notification_channels)
            if app.dynamic_analysis is None:
                app.dynamic_analysis = self.defaults.dynamic_analysis
        return self


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(str(e)) from e
