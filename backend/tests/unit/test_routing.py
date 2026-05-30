from app.agents.routing import model_for
from app.config import get_settings


def test_openai_key_enables_openai_provider(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_enabled is True
        assert settings.active_llm_provider == "openai"
        assert model_for("trivial") == settings.openai_model_trivial
    finally:
        get_settings.cache_clear()


def test_anthropic_still_supported(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_enabled is True
        assert settings.active_llm_provider == "anthropic"
        assert model_for("semantic") == settings.model_semantic
    finally:
        get_settings.cache_clear()


def test_forced_openai_requires_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_enabled is False
        assert settings.active_llm_provider is None
        assert model_for("final") is None
    finally:
        get_settings.cache_clear()
