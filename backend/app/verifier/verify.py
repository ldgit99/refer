"""F3 DOI and metadata verification.

For references that already include a DOI, verification checks three things:
  * the DOI URL resolves through doi.org;
  * the resolver returns usable metadata;
  * resolver/Crossref titles match the reference title above the configured gate.

For references without a DOI, Crossref bibliographic search is used to suggest
one when the metadata match is strong enough.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel
from rapidfuzz import fuzz

from app.citation.csl import CSLItem
from app.config import get_settings
from app.verifier.crossref import CrossrefClient

VerificationStatus = Literal[
    "verified",
    "doi_mismatch",
    "invalid_doi",
    "doi_suggested",
    "not_found",
    "skipped",
]

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


class VerifiedItem(BaseModel):
    ref_id: str
    status: VerificationStatus
    confidence: float = 0.0
    suggested_doi: str | None = None
    doi_url: str | None = None
    doi_resolves: bool | None = None
    title_matches: bool | None = None
    matched_title: str | None = None
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "INFO"
    note: str = ""


def extract_doi(text: str) -> str | None:
    m = DOI_RE.search(text or "")
    return m.group(0).rstrip(".,;)]}").lower() if m else None


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


async def _verify_existing_doi(
    ref: CSLItem,
    doi: str,
    client: CrossrefClient,
) -> VerifiedItem:
    settings = get_settings()
    doi_url = f"https://doi.org/{doi}"

    doi_resolves = await client.doi_url_resolves(doi)
    resolver_msg = await client.resolve_doi_csl(doi) if doi_resolves else None
    if resolver_msg is None:
        crossref_msg = await client.get_work(doi) if doi_resolves else None
        if crossref_msg is not None:
            crossref_meta = CSLItem.from_crossref(ref.id, crossref_msg)
            confidence, note = compare_metadata(ref, crossref_meta)
            title_matches = confidence >= settings.doi_title_confidence
            if title_matches:
                return VerifiedItem(
                    ref_id=ref.id,
                    status="verified",
                    confidence=confidence,
                    doi_url=doi_url,
                    doi_resolves=True,
                    title_matches=True,
                    matched_title=crossref_meta.title,
                    severity="INFO",
                    note=note or "DOI URL resolves; verified with Crossref metadata.",
                )
            return VerifiedItem(
                ref_id=ref.id,
                status="doi_mismatch",
                confidence=confidence,
                doi_url=doi_url,
                doi_resolves=True,
                title_matches=False,
                matched_title=crossref_meta.title,
                severity="WARNING",
                note=note
                or "DOI URL resolves, but Crossref title metadata does not match the reference title.",
            )

        return VerifiedItem(
            ref_id=ref.id,
            status="not_found" if doi_resolves else "invalid_doi",
            severity="WARNING" if doi_resolves else "CRITICAL",
            doi_url=doi_url,
            doi_resolves=doi_resolves,
            title_matches=None if doi_resolves else False,
            note=(
                "DOI URL resolves, but usable DOI metadata was not found."
                if doi_resolves
                else f"DOI URL {doi_url} did not resolve."
            ),
        )

    resolver_meta = CSLItem.from_csl_json(ref.id, resolver_msg)
    resolver_confidence, resolver_note = compare_metadata(ref, resolver_meta)
    resolver_title_matches = resolver_confidence >= settings.doi_title_confidence

    crossref_msg = await client.get_work(doi)
    if crossref_msg is None:
        return VerifiedItem(
            ref_id=ref.id,
            status="not_found",
            confidence=resolver_confidence,
            doi_url=doi_url,
            doi_resolves=True,
            title_matches=resolver_title_matches,
            matched_title=resolver_meta.title,
            severity="WARNING",
            note="DOI URL resolves, but Crossref did not return a work record.",
        )

    crossref_meta = CSLItem.from_crossref(ref.id, crossref_msg)
    crossref_confidence, crossref_note = compare_metadata(ref, crossref_meta)
    crossref_title_matches = crossref_confidence >= settings.doi_title_confidence
    confidence = max(resolver_confidence, crossref_confidence)
    matched_title = resolver_meta.title or crossref_meta.title
    note = "; ".join(n for n in (resolver_note, crossref_note) if n)

    if resolver_title_matches and crossref_title_matches:
        return VerifiedItem(
            ref_id=ref.id,
            status="verified",
            confidence=confidence,
            doi_url=doi_url,
            doi_resolves=True,
            title_matches=True,
            matched_title=matched_title,
            severity="INFO",
            note=note,
        )

    return VerifiedItem(
        ref_id=ref.id,
        status="doi_mismatch",
        confidence=confidence,
        doi_url=doi_url,
        doi_resolves=True,
        title_matches=False,
        matched_title=matched_title,
        severity="WARNING",
        note=note
        or "DOI URL resolves, but resolver/Crossref title metadata does not match the reference title.",
    )


async def verify_reference(ref: CSLItem, client: CrossrefClient) -> VerifiedItem:
    settings = get_settings()
    doi = ref.doi or extract_doi(ref.url) or extract_doi(ref.title)

    if doi:
        return await _verify_existing_doi(ref, doi, client)

    if not ref.title:
        return VerifiedItem(
            ref_id=ref.id,
            status="not_found",
            severity="WARNING",
            note="Missing title metadata.",
        )

    candidates = await client.search_bibliographic(ref.title, rows=5)
    best: tuple[float, CSLItem | None] = (0.0, None)
    for c in candidates:
        cand = CSLItem.from_crossref(ref.id, c)
        conf, _ = compare_metadata(ref, cand)
        if conf > best[0]:
            best = (conf, cand)

    if best[1] is not None and best[0] >= settings.doi_title_confidence:
        suggested_doi = best[1].doi or None
        return VerifiedItem(
            ref_id=ref.id,
            status="doi_suggested",
            confidence=best[0],
            suggested_doi=suggested_doi,
            doi_url=f"https://doi.org/{suggested_doi}" if suggested_doi else None,
            matched_title=best[1].title,
            title_matches=True,
            severity="INFO",
            note="Found a strong DOI candidate from bibliographic metadata.",
        )

    return VerifiedItem(
        ref_id=ref.id,
        status="not_found",
        confidence=best[0],
        title_matches=False,
        severity="WARNING",
        note="No sufficiently matching metadata record was found.",
    )
