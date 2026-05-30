"""Minimal OpenAI Chat Completions client used by optional review assists."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal, TypedDict

import httpx

from app.config import get_settings


class ChatMessage(TypedDict):
    role: Literal["developer", "system", "user", "assistant"]
    content: str


class OpenAIChatError(RuntimeError):
    pass


async def chat_json(
    messages: Sequence[ChatMessage],
    *,
    model: str | None = None,
    max_tokens: int = 1400,
    client: httpx.AsyncClient | None = None,
) -> dict:
    settings = get_settings()
    if settings.active_llm_provider != "openai" or not settings.openai_api_key:
        raise OpenAIChatError("OpenAI is not configured.")

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0)
    try:
        resp = await http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or settings.openai_model_semantic,
                "messages": list(messages),
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
    except httpx.HTTPError as exc:
        raise OpenAIChatError(f"OpenAI request failed: {exc.__class__.__name__}") from exc
    finally:
        if own_client:
            await http.aclose()

    if resp.status_code >= 400:
        raise OpenAIChatError(f"OpenAI returned HTTP {resp.status_code}.")

    payload = resp.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIChatError("OpenAI response did not contain message content.") from exc

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise OpenAIChatError("OpenAI response was not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise OpenAIChatError("OpenAI response JSON must be an object.")
    return parsed
