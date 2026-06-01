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
    openai_api_key: str | None = None
    llm_provider: str = "auto"
    crossref_polite_email: str | None = None
    kci_api_key: str | None = None
    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # F3 (external metadata verification). Disable to keep the pipeline offline
    # (tests, air-gapped demos). When enabled, references are checked against
    # Crossref/OpenAlex live.
    f3_enabled: bool = True
    # Max references verified concurrently (fan-out, research.md §7.7).
    f3_concurrency: int = 8
    # Use OpenAlex as a secondary verifier (preferred for Korean titles).
    openalex_enabled: bool = True

    # --- model routing (research.md §7.7) ---
    model_trivial: str = "claude-haiku-4-5"
    model_semantic: str = "claude-sonnet-4-6"
    model_final: str = "claude-opus-4-7"
    openai_model_trivial: str = "gpt-4.1-mini"
    openai_model_semantic: str = "gpt-4.1"
    openai_model_final: str = "gpt-4.1"

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
        """LLM critics run only when at least one provider API key is configured."""
        return self.active_llm_provider is not None

    @property
    def active_llm_provider(self) -> str | None:
        """Resolve the configured LLM provider.

        ``auto`` prefers OpenAI when ``OPENAI_API_KEY`` is present, then falls
        back to Anthropic for backward compatibility.
        """
        provider = self.llm_provider.lower().strip()
        if provider in {"none", "off", "disabled"}:
            return None
        if provider == "openai":
            return "openai" if self.openai_api_key else None
        if provider == "anthropic":
            return "anthropic" if self.anthropic_api_key else None
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
