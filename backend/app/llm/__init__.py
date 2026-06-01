"""LLM-assisted review helpers (provider-agnostic).

Routes to OpenAI or Anthropic based on the configured provider. Call sites should
import :func:`chat_json` from here rather than a provider module so the
deterministic pipeline keeps working when no key (or a different key) is set.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.config import get_settings
from app.llm.openai_client import ChatMessage


async def chat_json(
    messages: Sequence[ChatMessage],
    *,
    model: str | None = None,
    max_tokens: int = 1400,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Provider-agnostic JSON chat. Raises if no provider is configured."""
    provider = get_settings().active_llm_provider
    if provider == "anthropic":
        from app.llm.anthropic_client import chat_json as _anthropic_chat

        return await _anthropic_chat(
            messages, model=model, max_tokens=max_tokens, client=client
        )
    from app.llm.openai_client import chat_json as _openai_chat

    return await _openai_chat(
        messages, model=model, max_tokens=max_tokens, client=client
    )


def llm_configured() -> bool:
    return get_settings().active_llm_provider is not None


__all__ = ["ChatMessage", "chat_json", "llm_configured"]
