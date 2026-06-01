"""Minimal Anthropic Messages client mirroring the OpenAI JSON helper.

Lets the LLM-assisted review steps work when only ``ANTHROPIC_API_KEY`` is set
(LLM_PROVIDER=anthropic, or auto with no OpenAI key).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

import httpx

from app.config import get_settings
from app.llm.openai_client import ChatMessage

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicChatError(RuntimeError):
    pass


def _split_system(messages: Sequence[ChatMessage]) -> tuple[str, list[dict]]:
    system_parts: list[str] = []
    turns: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role in {"developer", "system"}:
            system_parts.append(msg["content"])
        else:
            turns.append({"role": "user" if role == "user" else "assistant", "content": msg["content"]})
    return "\n\n".join(system_parts), turns


def _extract_json(text: str) -> dict:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise AnthropicChatError("Anthropic response was not valid JSON.") from None
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise AnthropicChatError("Anthropic response was not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise AnthropicChatError("Anthropic response JSON must be an object.")
    return parsed


async def chat_json(
    messages: Sequence[ChatMessage],
    *,
    model: str | None = None,
    max_tokens: int = 1400,
    client: httpx.AsyncClient | None = None,
) -> dict:
    settings = get_settings()
    if settings.active_llm_provider != "anthropic" or not settings.anthropic_api_key:
        raise AnthropicChatError("Anthropic is not configured.")

    system, turns = _split_system(messages)
    if not turns:
        turns = [{"role": "user", "content": system}]
        system = ""

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0)
    try:
        resp = await http.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model or settings.model_semantic,
                "max_tokens": max_tokens,
                "temperature": 0,
                "system": system + "\n\nReturn JSON only." if system else "Return JSON only.",
                "messages": turns,
            },
        )
    except httpx.HTTPError as exc:
        raise AnthropicChatError(
            f"Anthropic request failed: {exc.__class__.__name__}"
        ) from exc
    finally:
        if own_client:
            await http.aclose()

    if resp.status_code >= 400:
        raise AnthropicChatError(f"Anthropic returned HTTP {resp.status_code}.")

    payload = resp.json()
    try:
        blocks = payload["content"]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except (KeyError, TypeError) as exc:
        raise AnthropicChatError("Anthropic response had no text content.") from exc
    return _extract_json(text)
