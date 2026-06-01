"""KCI / KISTI fallback hook (research.md §5.4).

Many Korea Citation Index (KCI) papers are absent from Crossref, producing
false ``not_found`` results for legitimate Korean references. This module
provides a thin, optional client: when ``KCI_API_KEY`` is configured it queries
the KCI Open API; otherwise it is a no-op so the pipeline degrades gracefully.

The KCI Open API schema varies by endpoint/version, so parsing here is
defensive and best-effort — it only needs to answer "does a plausibly matching
Korean record exist?" to downgrade a ``not_found`` to ``verified_external``.
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

KCI_SEARCH_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"


class KciClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    @property
    def enabled(self) -> bool:
        return bool(get_settings().kci_api_key)

    async def __aenter__(self) -> KciClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("KciClient must be used as an async context manager")
        return self._client

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(2),
        reraise=True,
    )
    async def search_title(self, title: str) -> list[dict]:
        """Search KCI by article title. Returns raw record dicts (possibly empty)."""
        settings = get_settings()
        if not settings.kci_api_key or not title.strip():
            return []
        resp = await self.client.get(
            KCI_SEARCH_URL,
            params={
                "apiCode": "articleSearch",
                "key": settings.kci_api_key,
                "title": title,
                "displayCount": "5",
            },
        )
        if resp.status_code >= 400:
            return []
        # KCI returns XML; do a light, dependency-free extraction of <title> tags.
        return _extract_records(resp.text)


def _extract_records(xml_text: str) -> list[dict]:
    import re

    records: list[dict] = []
    for m in re.finditer(r"<article[ >].*?</article>", xml_text, flags=re.DOTALL):
        block = m.group(0)
        title_m = re.search(r"<title[^>]*>(.*?)</title>", block, flags=re.DOTALL)
        doi_m = re.search(r"<doi[^>]*>(.*?)</doi>", block, flags=re.DOTALL)
        if title_m:
            records.append(
                {
                    "title": re.sub(r"<[^>]+>", "", title_m.group(1)).strip(),
                    "doi": (
                        re.sub(r"<[^>]+>", "", doi_m.group(1)).strip() if doi_m else ""
                    ),
                }
            )
    return records
