"""F3 verification logic (research.md §5.2, §5.3).

Compares a reference against Crossref metadata to decide existence, DOI validity,
and metadata agreement. Designed to be testable offline by injecting a client
(respx mocks the HTTP layer in tests).
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
    matched_title: str | None = None
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "INFO"
    note: str = ""


def extract_doi(text: str) -> str | None:
    m = DOI_RE.search(text or "")
    return m.group(0).rstrip(".").lower() if m else None


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
            notes.append(f"첫 저자 불일치({ref.author[0].family}≠{meta.author[0].family})")

    year_ok = True
    if ref.issued_year and meta.issued_year:
        year_ok = abs(ref.issued_year - meta.issued_year) <= 1
        if not year_ok:
            notes.append(f"연도 차이({ref.issued_year}≠{meta.issued_year})")

    confidence = title_sim
    if not author_ok:
        confidence *= 0.5
    if not year_ok:
        confidence *= 0.8
    return confidence, "; ".join(notes)


async def verify_reference(ref: CSLItem, client: CrossrefClient) -> VerifiedItem:
    settings = get_settings()
    doi = ref.doi or extract_doi(ref.title)

    if doi:
        meta_msg = await client.get_work(doi)
        if meta_msg is None:
            return VerifiedItem(
                ref_id=ref.id,
                status="invalid_doi",
                severity="CRITICAL",
                note=f"DOI {doi} 가 Crossref에 존재하지 않습니다.",
            )
        meta = CSLItem.from_crossref(ref.id, meta_msg)
        confidence, note = compare_metadata(ref, meta)
        if confidence >= settings.doi_title_confidence:
            return VerifiedItem(
                ref_id=ref.id,
                status="verified",
                confidence=confidence,
                matched_title=meta.title,
                severity="INFO",
                note=note,
            )
        return VerifiedItem(
            ref_id=ref.id,
            status="doi_mismatch",
            confidence=confidence,
            matched_title=meta.title,
            severity="WARNING",
            note=note or "DOI는 존재하나 메타데이터 일치도가 낮습니다.",
        )

    # No DOI: search to suggest one.
    if not ref.title:
        return VerifiedItem(
            ref_id=ref.id, status="not_found", severity="WARNING", note="제목 정보 없음"
        )
    candidates = await client.search_bibliographic(ref.title, rows=5)
    best: tuple[float, CSLItem | None] = (0.0, None)
    for c in candidates:
        cand = CSLItem.from_crossref(ref.id, c)
        conf, _ = compare_metadata(ref, cand)
        if conf > best[0]:
            best = (conf, cand)

    if best[1] is not None and best[0] >= settings.doi_title_confidence:
        return VerifiedItem(
            ref_id=ref.id,
            status="doi_suggested",
            confidence=best[0],
            suggested_doi=best[1].doi or None,
            matched_title=best[1].title,
            severity="INFO",
            note="DOI 자동 보완 후보를 찾았습니다.",
        )
    return VerifiedItem(
        ref_id=ref.id,
        status="not_found",
        confidence=best[0],
        severity="WARNING",
        note="외부 메타데이터에서 일치하는 문헌을 찾지 못했습니다.",
    )
