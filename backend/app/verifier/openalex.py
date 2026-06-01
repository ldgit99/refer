"""OpenAlex client (research.md §5.1).

Secondary verifier, preferred for Korean-language titles where Crossref coverage
is thin. Uses the polite pool via mailto query param.
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings

OPENALEX_BASE = "https://api.openalex.org"


def _params(extra: dict[str, str]) -> dict[str, str]:
    settings = get_settings()
    params = dict(extra)
    if settings.crossref_polite_email:
        params["mailto"] = settings.crossref_polite_email
    return params


class OpenAlexClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> OpenAlexClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OpenAlexClient must be used as an async context manager")
        return self._client

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def search(self, query: str, per_page: int = 5) -> list[dict]:
        resp = await self.client.get(
            f"{OPENALEX_BASE}/works",
            params=_params({"search": query, "per-page": str(per_page)}),
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def search_title(self, title: str, per_page: int = 5) -> list[dict]:
        """Title-scoped search; falls back to a general search on failure."""
        if not title.strip():
            return []
        try:
            resp = await self.client.get(
                f"{OPENALEX_BASE}/works",
                params=_params(
                    {"filter": f"title.search:{title}", "per-page": str(per_page)}
                ),
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return results
        except httpx.HTTPError:
            pass
        return await self.search(title, per_page=per_page)
