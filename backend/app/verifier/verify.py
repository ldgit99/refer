"""F3 — DOI link verification (scope: "does the DOI link open?").

This module intentionally does NOT compare titles/authors/years or suggest
missing DOIs. It answers one question per reference: **does the DOI resolve?**

  * verified   — the DOI link opens (doi.org redirects, or a metadata record
                 exists in Crossref / doi.org content negotiation).
  * invalid_doi — a DOI is present but the link does not open anywhere.
  * no_doi      — the reference has no DOI to check.
  * skipped     — the check was inconclusive (network/services unreachable).

A Crossref record or doi.org content-negotiation response also proves the link
is live, which matters because data-center IPs (serverless hosts) are frequently
bot-blocked from the publisher landing page — relying on the browser-style
resolve alone would produce false "link failed" results.
"""

from __future__ import annotations

import asyncio
import re
from typing import Literal
from urllib.parse import unquote

from pydantic import BaseModel

from app.citation.csl import CSLItem
from app.config import get_settings
from app.verifier.cache import get_verification_cache
from app.verifier.crossref import CrossrefClient

VerificationStatus = Literal[
    "verified",
    "invalid_doi",
    "no_doi",
    "skipped",
]

VerificationSource = Literal["crossref", "doi.org", "none"]

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.IGNORECASE)


class VerifiedItem(BaseModel):
    ref_id: str
    status: VerificationStatus
    doi: str | None = None
    doi_url: str | None = None
    doi_resolves: bool | None = None
    source: VerificationSource = "none"
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "INFO"
    note: str = ""


def _strip_trailing_doi_punctuation(doi: str) -> str:
    doi = doi.strip().rstrip(".,;")
    pairs = {")": "(", "]": "[", "}": "{"}
    while doi and doi[-1] in pairs and doi.count(pairs[doi[-1]]) < doi.count(doi[-1]):
        doi = doi[:-1].rstrip(".,;")
    return doi


def normalize_doi(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = unquote(str(text).strip())
    cleaned = re.sub(r"^(?:doi\s*:?\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^https?://(?:dx\.)?doi\.org/",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _strip_trailing_doi_punctuation(cleaned)
    if cleaned.lower().startswith("10."):
        return cleaned.lower()
    m = DOI_RE.search(cleaned)
    return _strip_trailing_doi_punctuation(m.group(0)).lower() if m else None


def extract_doi(text: str) -> str | None:
    return normalize_doi(text)


async def _doi_link_opens(doi: str, client: CrossrefClient) -> tuple[bool | None, VerificationSource]:
    """Return (opens, source). ``opens`` is None when the check is inconclusive.

    A positive signal from any of: doi.org browser resolve, doi.org content
    negotiation, or a Crossref record. Each call is independently tolerant of
    failures so a single bot-block/transient error does not cause a false fail.
    """
    # 1) Crossref record => DOI registered and resolvable.
    try:
        if await client.get_work(doi) is not None:
            return True, "crossref"
    except Exception:  # noqa: BLE001 - tolerate transient Crossref errors
        pass

    # 2) doi.org content negotiation => link lives and serves metadata.
    try:
        if await client.resolve_doi_csl(doi) is not None:
            return True, "doi.org"
    except Exception:  # noqa: BLE001 - resolver is best-effort
        pass

    # 3) Browser-style resolve (definitive negative only when it cleanly says no).
    try:
        opens = await client.doi_url_resolves(doi)
        return (True if opens else False), "doi.org"
    except Exception:  # noqa: BLE001 - bot-block / transient -> inconclusive
        return None, "none"


async def verify_reference(ref: CSLItem, client: CrossrefClient) -> VerifiedItem:
    """Verify that a reference's DOI link opens. No metadata comparison."""
    doi = normalize_doi(ref.doi) or extract_doi(ref.url) or extract_doi(ref.title)
    if not doi:
        return VerifiedItem(
            ref_id=ref.id,
            status="no_doi",
            doi=None,
            doi_url=None,
            doi_resolves=None,
            source="none",
            severity="INFO",
            note="No DOI present in this reference.",
        )

    doi_url = f"https://doi.org/{doi}"
    opens, source = await _doi_link_opens(doi, client)

    if opens is True:
        return VerifiedItem(
            ref_id=ref.id,
            status="verified",
            doi=doi,
            doi_url=doi_url,
            doi_resolves=True,
            source=source,
            severity="INFO",
            note="DOI link opens.",
        )
    if opens is False:
        return VerifiedItem(
            ref_id=ref.id,
            status="invalid_doi",
            doi=doi,
            doi_url=doi_url,
            doi_resolves=False,
            source="none",
            severity="CRITICAL",
            note=f"DOI link {doi_url} did not open.",
        )
    return VerifiedItem(
        ref_id=ref.id,
        status="skipped",
        doi=doi,
        doi_url=doi_url,
        doi_resolves=None,
        source="none",
        severity="WARNING",
        note="DOI link check was inconclusive (services unreachable).",
    )


def _cache_key(ref: CSLItem) -> str:
    doi = normalize_doi(ref.doi) or extract_doi(ref.url) or extract_doi(ref.title)
    return f"doi:{doi}" if doi else f"nodoi:{ref.id}"


async def verify_reference_cached(ref: CSLItem, client: CrossrefClient) -> VerifiedItem:
    """verify_reference with a process-local TTL cache (research.md §12.8)."""
    doi = normalize_doi(ref.doi) or extract_doi(ref.url) or extract_doi(ref.title)
    if not doi:
        return await verify_reference(ref, client)

    cache = get_verification_cache()
    key = _cache_key(ref)
    cached = await cache.get(key)
    if isinstance(cached, VerifiedItem):
        return cached.model_copy(update={"ref_id": ref.id})

    item = await verify_reference(ref, client)
    if item.status != "skipped":  # don't cache transient failures
        await cache.set(key, item)
    return item


def _skipped_item(ref: CSLItem, exc: Exception) -> VerifiedItem:
    detail = (str(exc).strip() or exc.__class__.__name__)[:180]
    doi = normalize_doi(ref.doi)
    return VerifiedItem(
        ref_id=ref.id,
        status="skipped",
        doi=doi,
        doi_url=f"https://doi.org/{doi}" if doi else None,
        doi_resolves=None,
        source="none",
        severity="WARNING",
        note=f"DOI link check could not be completed: {detail}",
    )


async def verify_references(
    refs: list[CSLItem],
    client: CrossrefClient,
    *,
    concurrency: int | None = None,
) -> dict[str, VerifiedItem]:
    """Verify DOI links concurrently (fan-out, research.md §7.7).

    Bounded by a semaphore to respect Crossref's polite-pool limit and serverless
    time budgets. Per-item failures are isolated.
    """
    settings = get_settings()
    limit = concurrency or settings.f3_concurrency
    semaphore = asyncio.Semaphore(max(1, limit))

    async def _one(ref: CSLItem) -> tuple[str, VerifiedItem]:
        async with semaphore:
            try:
                item = await verify_reference_cached(ref, client)
            except Exception as exc:  # noqa: BLE001 - per-item resilience
                item = _skipped_item(ref, exc)
            return ref.id, item

    results = await asyncio.gather(*[_one(r) for r in refs])
    return dict(results)
