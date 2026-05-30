import httpx
import pytest

from app.config import Settings
from app.llm.health import check_llm_health


class FakeAsyncClient:
    def __init__(self, response: httpx.Response | None = None, exc: httpx.HTTPError | None = None):
        self.response = response
        self.exc = exc
        self.request: tuple[str, dict[str, str]] | None = None

    async def get(self, url: str, headers: dict[str, str]):
        self.request = (url, headers)
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


@pytest.mark.asyncio
async def test_openai_llm_health_ok() -> None:
    settings = Settings(openai_api_key="sk-test", llm_provider="openai")
    client = FakeAsyncClient(httpx.Response(200, json={"id": settings.openai_model_trivial}))

    result = await check_llm_health(settings=settings, client=client)

    assert result.status == "ok"
    assert result.provider == "openai"
    assert result.model == settings.openai_model_trivial
    assert client.request is not None
    assert client.request[1]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_openai_llm_health_error_sanitizes_response() -> None:
    settings = Settings(openai_api_key="bad-key", llm_provider="openai")
    client = FakeAsyncClient(
        httpx.Response(
            401,
            json={"error": {"type": "invalid_request_error", "message": "Incorrect API key."}},
        )
    )

    result = await check_llm_health(settings=settings, client=client)

    assert result.status == "error"
    assert result.provider == "openai"
    assert result.model == settings.openai_model_trivial
    assert "invalid_request_error" in result.detail
    assert "Incorrect API key" not in result.detail
    assert "bad-key" not in result.detail


@pytest.mark.asyncio
async def test_llm_health_disabled_without_key() -> None:
    settings = Settings(llm_provider="openai")

    result = await check_llm_health(settings=settings)

    assert result.status == "disabled"
