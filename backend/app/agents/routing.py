"""Model routing (research.md §7.7, plan.md M6).

Maps a task difficulty class to the active provider's model. Returns None when
no API key is configured so callers fall back to the deterministic path.
"""

from __future__ import annotations

from typing import Literal

from app.config import get_settings

TaskClass = Literal["trivial", "semantic", "final"]


def model_for(task: TaskClass) -> str | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    if settings.active_llm_provider == "openai":
        return {
            "trivial": settings.openai_model_trivial,
            "semantic": settings.openai_model_semantic,
            "final": settings.openai_model_final,
        }[task]
    return {
        "trivial": settings.model_trivial,
        "semantic": settings.model_semantic,
        "final": settings.model_final,
    }[task]


def llm_available() -> bool:
    return get_settings().llm_enabled


def llm_provider() -> str | None:
    return get_settings().active_llm_provider
