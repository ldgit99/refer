"""Full review orchestration producing a report + patch proposals (M2).

This is the deterministic pipeline that M3 wraps in LangGraph. It returns a
``ReviewResult`` carrying the F1 match report, F2 APA formatting, optional F3
verification, and the list of patch proposals the user can accept/reject.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.citation.csl import CSLItem
from app.citation.extractor import extract_citations
from app.citation.formatter import format_apa
from app.citation.matcher import MatchReport, match
from app.citation.ref_to_csl import reference_to_csl
from app.citation.references import ReferenceItem, parse_references
from app.parsers.base import ParsedDocument
from app.verifier.crossref import CrossrefClient
from app.verifier.verify import VerifiedItem, verify_reference
from app.writers.base import ParagraphRef, Patch

MAX_VERIFICATION_ERROR_LEN = 180


class ReviewResult(BaseModel):
    match_report: MatchReport
    csl_items: list[CSLItem] = Field(default_factory=list)
    formatted: dict[str, str] = Field(default_factory=dict)  # ref_id -> APA string
    verified: dict[str, VerifiedItem] = Field(default_factory=dict)
    patches: list[Patch] = Field(default_factory=list)


def _ref_paragraph_index(document: ParsedDocument, ref: ReferenceItem) -> int:
    """Best-effort map a reference entry back to its paragraph index."""
    ref_paras = document.reference_paragraphs()
    for p in ref_paras:
        if ref.raw[:30] and ref.raw[:30] in p.text:
            return p.index
    if document.references_start_index is not None:
        return document.references_start_index + 1 + ref.index
    return ref.index


def build_patches(
    document: ParsedDocument,
    report: MatchReport,
    formatted: dict[str, str],
    csl_items: list[CSLItem],
    verified: dict[str, VerifiedItem],
) -> list[Patch]:
    patches: list[Patch] = []

    # F2: reference_replace when APA formatting differs from the original.
    for ref in report.references:
        ref_id = f"ref-{ref.index}"
        apa = formatted.get(ref_id)
        if not apa:
            continue
        if apa.strip() and apa.strip() != ref.raw.strip():
            patches.append(
                Patch(
                    id=f"f2-{ref.index}",
                    kind="reference_replace",
                    target=ParagraphRef(paragraph_index=_ref_paragraph_index(document, ref)),
                    before=ref.raw,
                    after=apa,
                    confidence=0.9,
                    source="F2",
                    severity="INFO",
                    comment="APA 7판 형식으로 변환",
                )
            )

    # F3: doi_insert / warnings.
    for ref in report.references:
        ref_id = f"ref-{ref.index}"
        v = verified.get(ref_id)
        if not v:
            continue
        if v.status == "doi_suggested" and v.suggested_doi:
            patches.append(
                Patch(
                    id=f"f3-{ref.index}",
                    kind="doi_insert",
                    target=ParagraphRef(paragraph_index=_ref_paragraph_index(document, ref)),
                    before=ref.raw,
                    after=f"{ref.raw} https://doi.org/{v.suggested_doi}",
                    confidence=v.confidence,
                    source="F3",
                    severity="INFO",
                    comment="DOI 자동 보완",
                )
            )
        elif v.status in {"invalid_doi", "doi_mismatch", "not_found", "skipped"}:
            patches.append(
                Patch(
                    id=f"f3warn-{ref.index}",
                    kind="citation_comment",
                    target=ParagraphRef(paragraph_index=_ref_paragraph_index(document, ref)),
                    before=ref.raw,
                    comment=f"[F3 {v.status}] {v.note}",
                    confidence=0.6,
                    source="F3",
                    severity=v.severity,
                )
            )

    # F1: citation_comment for orphan / mismatch issues anchored in body text.
    for i, issue in enumerate(report.issues):
        if issue.paragraph_index is None:
            continue
        if issue.type in {"orphan_citation", "year_mismatch", "author_count_mismatch"}:
            patches.append(
                Patch(
                    id=f"f1-{i}",
                    kind="citation_comment",
                    target=ParagraphRef(
                        paragraph_index=issue.paragraph_index,
                        char_start=issue.char_start,
                        char_end=issue.char_end,
                    ),
                    before=issue.citation_raw or "",
                    comment=f"[F1 {issue.type}] {issue.message}",
                    confidence=0.95 if issue.severity == "CRITICAL" else 0.8,
                    source="F1",
                    severity=issue.severity,
                )
            )

    return patches


def _f1_f2(document: ParsedDocument) -> tuple[MatchReport, list[CSLItem], dict[str, str]]:
    citations = extract_citations(document)
    references = parse_references(document.references_section)
    report = match(citations, references)
    csl_items = [reference_to_csl(r) for r in references]
    formatted = {c.id: format_apa(c) for c in csl_items}
    return report, csl_items, formatted


def _verification_failure_item(ref: CSLItem, exc: Exception) -> VerifiedItem:
    detail = str(exc).strip() or exc.__class__.__name__
    if len(detail) > MAX_VERIFICATION_ERROR_LEN:
        detail = f"{detail[:MAX_VERIFICATION_ERROR_LEN].rstrip()}..."
    doi_url = f"https://doi.org/{ref.doi}" if ref.doi else None
    return VerifiedItem(
        ref_id=ref.id,
        status="skipped",
        severity="WARNING",
        doi_url=doi_url,
        doi_resolves=False if ref.doi else None,
        title_matches=False if ref.doi else None,
        note=f"DOI verification could not be completed: {detail}",
    )


def review_sync(document: ParsedDocument) -> ReviewResult:
    """F1 + F2 only (no network)."""
    report, csl_items, formatted = _f1_f2(document)
    patches = build_patches(document, report, formatted, csl_items, verified={})
    return ReviewResult(
        match_report=report,
        csl_items=csl_items,
        formatted=formatted,
        verified={},
        patches=patches,
    )


async def review_with_verification(
    document: ParsedDocument,
    client: CrossrefClient | None = None,
) -> ReviewResult:
    """Full F1 + F2 + F3 review. Skips F3 gracefully when disabled or offline."""
    from app.config import get_settings

    report, csl_items, formatted = _f1_f2(document)
    verified: dict[str, VerifiedItem] = {}

    if client is None and not get_settings().f3_enabled:
        patches = build_patches(document, report, formatted, csl_items, verified)
        return ReviewResult(
            match_report=report,
            csl_items=csl_items,
            formatted=formatted,
            verified=verified,
            patches=patches,
        )

    own_client = client is None
    try:
        cr = client or CrossrefClient()
        if own_client:
            await cr.__aenter__()
        try:
            for c in csl_items:
                try:
                    verified[c.id] = await verify_reference(c, cr)
                except Exception as exc:  # noqa: BLE001 - per-item resilience
                    verified[c.id] = _verification_failure_item(c, exc)
        finally:
            if own_client:
                await cr.__aexit__(None, None, None)
    except Exception as exc:  # noqa: BLE001 - F3 is best-effort
        verified = {c.id: _verification_failure_item(c, exc) for c in csl_items}

    patches = build_patches(document, report, formatted, csl_items, verified)
    return ReviewResult(
        match_report=report,
        csl_items=csl_items,
        formatted=formatted,
        verified=verified,
        patches=patches,
    )
