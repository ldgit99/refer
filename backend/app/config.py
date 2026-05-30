"""Central configuration and tunable thresholds.

All hyperparameters that affect matching/verification behaviour live here so they
can be tuned against the regression set (see plan.md M6/M7) in one place.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- service ---
    app_name: str = "refer-backend"
    environment: str = "development"
    cors_origins: str = "http://localhost:3000"

    # --- external services ---
    anthropic_api_key: str | None = None
    crossref_polite_email: str | None = None
    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # --- model routing (research.md §7.7) ---
    model_trivial: str = "claude-haiku-4-5"
    model_semantic: str = "claude-sonnet-4-6"
    model_final: str = "claude-opus-4-7"

    # --- tunable thresholds (plan.md M6 §3) ---
    fuzzy_match_threshold: float = 0.85
    doi_title_confidence: float = 0.92
    critic_revision_max: int = 3
    hitl_confidence_gate: float = 0.7

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        """LLM critics run only when an API key is configured."""
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
