"""Crossref REST client (research.md §5).

Uses the polite pool (mailto) when an email is configured, with tenacity
exponential backoff for transient failures / 429s.
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

CROSSREF_BASE = "https://api.crossref.org"


def _headers() -> dict[str, str]:
    settings = get_settings()
    ua = "refer/0.1 (https://github.com/ldgit99/refer)"
    if settings.crossref_polite_email:
        ua += f" mailto:{settings.crossref_polite_email}"
    return {"User-Agent": ua}


def _params(extra: dict[str, str]) -> dict[str, str]:
    settings = get_settings()
    params = dict(extra)
    if settings.crossref_polite_email:
        params["mailto"] = settings.crossref_polite_email
    return params


class CrossrefClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> CrossrefClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0, headers=_headers())
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("CrossrefClient must be used as an async context manager")
        return self._client

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def get_work(self, doi: str) -> dict | None:
        """Fetch a work by DOI. Returns the Crossref ``message`` or None (404)."""
        doi_norm = doi.strip().lower()
        resp = await self.client.get(
            f"{CROSSREF_BASE}/works/{doi_norm}", params=_params({})
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("message")

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def doi_url_resolves(self, doi: str) -> bool:
        """Check whether the DOI URL resolves like a browser link."""
        doi_norm = doi.strip().lower()
        resp = await self.client.get(
            f"https://doi.org/{doi_norm}",
            headers={**_headers(), "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=False,
        )
        return 200 <= resp.status_code < 400

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def resolve_doi_csl(self, doi: str) -> dict | None:
        """Resolve a DOI URL and request CSL JSON metadata from doi.org."""
        doi_norm = doi.strip().lower()
        resp = await self.client.get(
            f"https://doi.org/{doi_norm}",
            headers={
                **_headers(),
                "Accept": "application/vnd.citationstyles.csl+json",
            },
            follow_redirects=True,
        )
        if resp.status_code in {404, 410}:
            return None
        resp.raise_for_status()
        if "json" not in resp.headers.get("content-type", ""):
            return None
        return resp.json()

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def search_bibliographic(self, query: str, rows: int = 5) -> list[dict]:
        """Search works by free-form bibliographic string."""
        resp = await self.client.get(
            f"{CROSSREF_BASE}/works",
            params=_params({"query.bibliographic": query, "rows": str(rows)}),
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("items", [])
