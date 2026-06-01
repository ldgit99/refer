"""F3 DOI and metadata verification.

For references that already include a DOI, verification checks three things:
  * the DOI URL resolves through doi.org;
  * the resolver returns usable metadata;
  * resolver/Crossref titles match the reference title above the configured gate.

For references without a DOI, Crossref bibliographic search is used to suggest
one when the metadata match is strong enough.
"""

from __future__ import annotations

import asyncio
import re
from typing import Literal
from urllib.parse import unquote

from pydantic import BaseModel
from rapidfuzz import fuzz

from app.citation.csl import CSLItem
from app.config import get_settings
from app.verifier.cache import get_verification_cache
from app.verifier.crossref import CrossrefClient
from app.verifier.kci import KciClient
from app.verifier.openalex import OpenAlexClient

VerificationStatus = Literal[
    "verified",
    "verified_weak",
    "verified_external",
    "doi_mismatch",
    "invalid_doi",
    "doi_suggested",
    "not_found",
    "skipped",
]

VerificationSource = Literal["crossref", "doi.org", "openalex", "kci", "none"]

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.IGNORECASE)


class VerifiedItem(BaseModel):
    ref_id: str
    status: VerificationStatus
    confidence: float = 0.0
    suggested_doi: str | None = None
    doi_url: str | None = None
    doi_resolves: bool | None = None
    title_matches: bool | None = None
    matched_title: str | None = None
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


def _norm_title(t: str) -> str:
    return re.sub(r"[^\w\s]", "", (t or "").lower()).strip()


def title_similarity(a: str, b: str) -> float:
    return fuzz.WRatio(_norm_title(a), _norm_title(b)) / 100.0


def compare_metadata(ref: CSLItem, meta: CSLItem) -> tuple[float, str]:
    """Return (confidence, note) comparing a reference to candidate metadata."""
    title_sim = title_similarity(ref.title, meta.title) if ref.title else 0.0
    notes: list[str] = []

    author_ok = True
    if ref.author and meta.author:
        ref_first = ref.author[0].family.lower()
        meta_first = meta.author[0].family.lower()
        author_ok = fuzz.ratio(ref_first, meta_first) >= 80
        if not author_ok:
            notes.append(
                f"first author mismatch ({ref.author[0].family} vs {meta.author[0].family})"
            )

    year_ok = True
    if ref.issued_year and meta.issued_year:
        year_ok = abs(ref.issued_year - meta.issued_year) <= 1
        if not year_ok:
            notes.append(f"year mismatch ({ref.issued_year} vs {meta.issued_year})")

    confidence = title_sim
    if not author_ok:
        confidence *= 0.5
    if not year_ok:
        confidence *= 0.8
    return confidence, "; ".join(notes)


def _classify_doi_match(
    ref_id: str,
    confidence: float,
    matched_title: str | None,
    doi_url: str,
    doi_resolves: bool | None,
    source: VerificationSource,
    note: str,
) -> VerifiedItem:
    """Band a DOI-with-metadata result into verified / weak / mismatch.

    The DOI is known to exist (a metadata record was returned), so this never
    produces a CRITICAL ``invalid_doi`` — only how strongly the *title* matches.
    """
    settings = get_settings()
    if confidence >= settings.doi_title_confidence:
        return VerifiedItem(
            ref_id=ref_id,
            status="verified",
            confidence=confidence,
            doi_url=doi_url,
            doi_resolves=doi_resolves,
            title_matches=True,
            matched_title=matched_title,
            source=source,
            severity="INFO",
            note=note or "DOI exists and the title matches.",
        )
    if confidence >= settings.doi_title_weak:
        return VerifiedItem(
            ref_id=ref_id,
            status="verified_weak",
            confidence=confidence,
            doi_url=doi_url,
            doi_resolves=doi_resolves,
            title_matches=True,
            matched_title=matched_title,
            source=source,
            severity="INFO",
            note=note
            or "DOI exists; title is a probable (not exact) match — please confirm.",
        )
    return VerifiedItem(
        ref_id=ref_id,
        status="doi_mismatch",
        confidence=confidence,
        doi_url=doi_url,
        doi_resolves=doi_resolves,
        title_matches=False,
        matched_title=matched_title,
        source=source,
        severity="WARNING",
        note=note or "DOI exists, but its title does not match the reference.",
    )


async def _verify_existing_doi(
    ref: CSLItem,
    doi: str,
    client: CrossrefClient,
) -> VerifiedItem:
    """Verify a reference that already carries a DOI.

    Strategy (Crossref-first): a record in Crossref OR doi.org content
    negotiation proves the DOI is *registered*, so existence does not depend on
    fetching the publisher landing page — which data-center IPs (e.g. serverless
    hosts) are frequently bot-blocked from, causing false "link failed" results.
    The browser-style resolve check is only **corroborating**: it can upgrade
    ``doi_resolves`` to True but never downgrades an otherwise-valid DOI.
    """
    doi = normalize_doi(doi) or doi
    doi_url = f"https://doi.org/{doi}"

    # 1) Authoritative existence checks (metadata), tolerant of failures.
    crossref_meta: CSLItem | None = None
    resolver_meta: CSLItem | None = None
    try:
        crossref_msg = await client.get_work(doi)
        if crossref_msg is not None:
            crossref_meta = CSLItem.from_crossref(ref.id, crossref_msg)
    except Exception:  # noqa: BLE001 - tolerate transient Crossref errors
        crossref_meta = None
    try:
        resolver_msg = await client.resolve_doi_csl(doi)
        if resolver_msg is not None:
            resolver_meta = CSLItem.from_csl_json(ref.id, resolver_msg)
    except Exception:  # noqa: BLE001 - resolver is best-effort
        resolver_meta = None

    # 2) Corroborating browser-style resolve (never the sole basis for a verdict).
    try:
        url_ok: bool | None = await client.doi_url_resolves(doi)
    except Exception:  # noqa: BLE001 - bot-blocking / transient failures are expected
        url_ok = None

    has_metadata = crossref_meta is not None or resolver_meta is not None
    # The DOI is considered to resolve if any signal is positive.
    doi_resolves = True if (has_metadata or url_ok) else (False if url_ok is False else None)

    if has_metadata:
        best_conf = -1.0
        best_meta: CSLItem | None = None
        best_source: VerificationSource = "crossref"
        notes: list[str] = []
        for meta, source in ((crossref_meta, "crossref"), (resolver_meta, "doi.org")):
            if meta is None:
                continue
            conf, note = compare_metadata(ref, meta)
            if note:
                notes.append(note)
            if conf > best_conf:
                best_conf, best_meta, best_source = conf, meta, source  # type: ignore[assignment]
        return _classify_doi_match(
            ref.id,
            best_conf,
            best_meta.title if best_meta else None,
            doi_url,
            doi_resolves,
            best_source,
            "; ".join(dict.fromkeys(notes)),
        )

    # 3) No metadata anywhere. Distinguish a registered-but-opaque DOI from a
    #    genuinely invalid one using the resolve signal.
    if url_ok:
        return VerifiedItem(
            ref_id=ref.id,
            status="verified_weak",
            confidence=0.0,
            doi_url=doi_url,
            doi_resolves=True,
            title_matches=None,
            source="doi.org",
            severity="INFO",
            note="DOI link resolves, but no machine-readable metadata was returned.",
        )
    if url_ok is False:
        return VerifiedItem(
            ref_id=ref.id,
            status="invalid_doi",
            confidence=0.0,
            doi_url=doi_url,
            doi_resolves=False,
            title_matches=False,
            source="none",
            severity="CRITICAL",
            note=f"DOI link {doi_url} did not resolve and no metadata was found.",
        )
    # All checks were inconclusive (network/bot-block): do not raise a false alarm.
    return VerifiedItem(
        ref_id=ref.id,
        status="skipped",
        confidence=0.0,
        doi_url=doi_url,
        doi_resolves=None,
        title_matches=None,
        source="none",
        severity="WARNING",
        note="DOI verification was inconclusive (metadata services unreachable).",
    )


async def _search_best_crossref(
    ref: CSLItem, client: CrossrefClient
) -> tuple[float, CSLItem | None]:
    candidates = await client.search_bibliographic(ref.title, rows=5)
    best: tuple[float, CSLItem | None] = (0.0, None)
    for c in candidates:
        cand = CSLItem.from_crossref(ref.id, c)
        conf, _ = compare_metadata(ref, cand)
        if conf > best[0]:
            best = (conf, cand)
    return best


async def _search_best_openalex(
    ref: CSLItem, client: OpenAlexClient
) -> tuple[float, CSLItem | None]:
    results = await client.search_title(ref.title, per_page=5)
    best: tuple[float, CSLItem | None] = (0.0, None)
    for work in results:
        cand = CSLItem.from_openalex(ref.id, work)
        conf, _ = compare_metadata(ref, cand)
        if conf > best[0]:
            best = (conf, cand)
    return best


def _doi_suggested_item(ref_id: str, score: float, cand: CSLItem, source: str) -> VerifiedItem:
    suggested_doi = cand.doi or None
    return VerifiedItem(
        ref_id=ref_id,
        status="doi_suggested",
        confidence=score,
        suggested_doi=suggested_doi,
        doi_url=f"https://doi.org/{suggested_doi}" if suggested_doi else None,
        matched_title=cand.title,
        title_matches=True,
        source=source,  # type: ignore[arg-type]
        severity="INFO",
        note=f"Found a strong DOI candidate from {source} metadata.",
    )


async def verify_reference(
    ref: CSLItem,
    client: CrossrefClient,
    *,
    openalex: OpenAlexClient | None = None,
    kci: KciClient | None = None,
) -> VerifiedItem:
    settings = get_settings()
    doi = normalize_doi(ref.doi) or extract_doi(ref.url) or extract_doi(ref.title)

    if doi:
        return await _verify_existing_doi(ref, doi, client)

    if not ref.title:
        return VerifiedItem(
            ref_id=ref.id,
            status="not_found",
            severity="WARNING",
            source="none",
            note="Missing title metadata.",
        )

    # No DOI: search Crossref first, then OpenAlex (stronger for Korean titles).
    best_score, best_cand = await _search_best_crossref(ref, client)
    best_source = "crossref"
    if best_score < settings.doi_title_confidence and openalex is not None:
        oa_score, oa_cand = await _search_best_openalex(ref, openalex)
        if oa_score > best_score:
            best_score, best_cand, best_source = oa_score, oa_cand, "openalex"

    if best_cand is not None and best_score >= settings.doi_title_confidence:
        return _doi_suggested_item(ref.id, best_score, best_cand, best_source)

    # KCI fallback: confirm a Korean record exists even without a DOI.
    if kci is not None and kci.enabled:
        try:
            records = await kci.search_title(ref.title)
        except Exception:  # noqa: BLE001 - KCI is best-effort
            records = []
        for rec in records:
            if title_similarity(ref.title, rec.get("title", "")) >= settings.doi_title_confidence:
                kci_doi = normalize_doi(rec.get("doi"))
                return VerifiedItem(
                    ref_id=ref.id,
                    status="verified_external",
                    confidence=max(best_score, settings.doi_title_confidence),
                    suggested_doi=kci_doi,
                    doi_url=f"https://doi.org/{kci_doi}" if kci_doi else None,
                    matched_title=rec.get("title"),
                    title_matches=True,
                    source="kci",
                    severity="INFO",
                    note="Matched a KCI (Korea Citation Index) record.",
                )

    return VerifiedItem(
        ref_id=ref.id,
        status="not_found",
        confidence=best_score,
        title_matches=False,
        source="none",
        severity="WARNING",
        note="No sufficiently matching metadata record was found.",
    )


def _cache_key(ref: CSLItem) -> str:
    doi = normalize_doi(ref.doi) or extract_doi(ref.url) or extract_doi(ref.title)
    if doi:
        return f"doi:{doi}"
    title = _norm_title(ref.title)
    first_author = ref.author[0].family.lower() if ref.author else ""
    return f"t:{first_author}|{title}|{ref.issued_year or ''}"


async def verify_reference_cached(
    ref: CSLItem,
    client: CrossrefClient,
    *,
    openalex: OpenAlexClient | None = None,
    kci: KciClient | None = None,
) -> VerifiedItem:
    """verify_reference with a process-local TTL cache (research.md §12.8)."""
    cache = get_verification_cache()
    key = _cache_key(ref)

    cached = await cache.get(key)
    if isinstance(cached, VerifiedItem):
        return cached.model_copy(update={"ref_id": ref.id})

    item = await verify_reference(ref, client, openalex=openalex, kci=kci)
    # Only cache deterministic outcomes (avoid caching transient skips).
    if item.status != "skipped":
        await cache.set(key, item)
    return item


async def verify_references(
    refs: list[CSLItem],
    client: CrossrefClient,
    *,
    openalex: OpenAlexClient | None = None,
    kci: KciClient | None = None,
    concurrency: int | None = None,
) -> dict[str, VerifiedItem]:
    """Verify references concurrently (fan-out, research.md §7.7).

    Bounded by a semaphore to stay within Crossref's polite-pool rate limit and
    serverless time budgets. Per-item failures are isolated by the caller.
    """
    settings = get_settings()
    limit = concurrency or settings.f3_concurrency
    semaphore = asyncio.Semaphore(max(1, limit))

    async def _one(ref: CSLItem) -> tuple[str, VerifiedItem]:
        async with semaphore:
            try:
                item = await verify_reference_cached(
                    ref, client, openalex=openalex, kci=kci
                )
            except Exception as exc:  # noqa: BLE001 - per-item resilience
                item = _skipped_item(ref, exc)
            return ref.id, item

    results = await asyncio.gather(*[_one(r) for r in refs])
    return dict(results)


def _skipped_item(ref: CSLItem, exc: Exception) -> VerifiedItem:
    detail = (str(exc).strip() or exc.__class__.__name__)[:180]
    doi = normalize_doi(ref.doi)
    return VerifiedItem(
        ref_id=ref.id,
        status="skipped",
        severity="WARNING",
        doi_url=f"https://doi.org/{doi}" if doi else None,
        doi_resolves=False if doi else None,
        title_matches=False if doi else None,
        source="none",
        note=f"DOI verification could not be completed: {detail}",
    )
