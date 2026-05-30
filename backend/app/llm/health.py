"""Safe LLM provider connectivity checks."""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel

from app.config import Settings, get_settings


class LLMHealth(BaseModel):
    status: Literal["ok", "disabled", "unsupported", "error"]
    provider: str | None = None
    model: str | None = None
    detail: str = ""


def _safe_error_detail(resp: httpx.Response) -> str:
    fallback = f"OpenAI API returned HTTP {resp.status_code}."
    try:
        payload = resp.json()
    except ValueError:
        return fallback

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code") or error.get("type")
        if code:
            return f"OpenAI API returned HTTP {resp.status_code} ({code})."
    return fallback


async def check_llm_health(
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> LLMHealth:
    settings = settings or get_settings()
    provider = settings.active_llm_provider

    if provider is None:
        return LLMHealth(status="disabled", detail="No LLM API key is configured.")

    if provider != "openai":
        return LLMHealth(
            status="unsupported",
            provider=provider,
            detail="Live health checks are currently implemented for OpenAI only.",
        )

    model = settings.openai_model_trivial
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await http.get(f"https://api.openai.com/v1/models/{model}", headers=headers)
    except httpx.HTTPError as exc:
        return LLMHealth(
            status="error",
            provider="openai",
            model=model,
            detail=f"OpenAI API request failed: {exc.__class__.__name__}",
        )
    finally:
        if own_client:
            await http.aclose()

    if resp.status_code == 200:
        return LLMHealth(
            status="ok",
            provider="openai",
            model=model,
            detail="OpenAI API key and model access verified.",
        )

    return LLMHealth(
        status="error",
        provider="openai",
        model=model,
        detail=_safe_error_detail(resp),
    )
