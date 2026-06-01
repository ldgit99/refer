"""Review orchestration — two features only.

  F1: do in-text citations and the reference list match (orphans, year, et al.,
      duplicates)?
  F3: does each reference's DOI link open?

APA re-formatting (the former F2) and DOI metadata/title comparison have been
intentionally removed: the tool reports matching problems and dead DOI links,
nothing more.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.citation.csl import CSLItem
from app.citation.extractor import extract_citations
from app.citation.matcher import MatchReport, match
from app.citation.ref_to_csl import reference_to_csl
from app.citation.references import ReferenceItem, parse_references
from app.config import get_settings
from app.llm.reference_parser import refine_references_with_llm
from app.parsers.base import ParsedDocument
from app.verifier.crossref import CrossrefClient
from app.verifier.verify import VerifiedItem, verify_references
from app.writers.base import ParagraphRef, Patch

MAX_VERIFICATION_ERROR_LEN = 180


class ReviewResult(BaseModel):
    match_report: MatchReport
    csl_items: list[CSLItem] = Field(default_factory=list)
    verified: dict[str, VerifiedItem] = Field(default_factory=dict)
    patches: list[Patch] = Field(default_factory=list)
    llm_used: bool = False


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
    csl_items: list[CSLItem],
    verified: dict[str, VerifiedItem],
) -> list[Patch]:
    """Build review comments for the two features.

    F1: a citation_comment on each matching problem in the body text.
    F3: a citation_comment on each reference whose DOI link does not open.
    """
    patches: list[Patch] = []

    # F1: matching problems anchored in the body text.
    for i, issue in enumerate(report.issues):
        if issue.paragraph_index is None:
            continue
        if issue.type in {
            "orphan_citation",
            "year_mismatch",
            "author_count_mismatch",
            "duplicate_reference",
        }:
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

    # F3: flag references whose DOI link does not open.
    for ref in report.references:
        v = verified.get(f"ref-{ref.index}")
        if v is None or v.status not in {"invalid_doi", "skipped"}:
            continue
        patches.append(
            Patch(
                id=f"f3-{ref.index}",
                kind="citation_comment",
                target=ParagraphRef(paragraph_index=_ref_paragraph_index(document, ref)),
                before=ref.raw,
                comment=f"[F3 {v.status}] {v.note}",
                confidence=0.9 if v.status == "invalid_doi" else 0.5,
                source="F3",
                severity=v.severity,
            )
        )

    return patches


def _f1(document: ParsedDocument) -> tuple[MatchReport, list[CSLItem]]:
    citations = extract_citations(document)
    references = parse_references(document.references_section)
    report = match(citations, references)
    csl_items = [reference_to_csl(r) for r in references]
    return report, csl_items


async def _f1_with_optional_llm(
    document: ParsedDocument,
) -> tuple[MatchReport, list[CSLItem], bool]:
    citations = extract_citations(document)
    references = parse_references(document.references_section)
    references, csl_items, llm_used = await refine_references_with_llm(references)
    report = match(citations, references)
    return report, csl_items, llm_used


def _verification_failure_item(ref: CSLItem, exc: Exception) -> VerifiedItem:
    detail = str(exc).strip() or exc.__class__.__name__
    if len(detail) > MAX_VERIFICATION_ERROR_LEN:
        detail = f"{detail[:MAX_VERIFICATION_ERROR_LEN].rstrip()}..."
    doi = ref.doi or None
    return VerifiedItem(
        ref_id=ref.id,
        status="skipped",
        severity="WARNING",
        doi=doi,
        doi_url=f"https://doi.org/{doi}" if doi else None,
        doi_resolves=None,
        note=f"DOI link check could not be completed: {detail}",
    )


def review_sync(document: ParsedDocument) -> ReviewResult:
    """F1 only (no network)."""
    report, csl_items = _f1(document)
    patches = build_patches(document, report, csl_items, verified={})
    return ReviewResult(
        match_report=report,
        csl_items=csl_items,
        verified={},
        patches=patches,
        llm_used=False,
    )


async def review_with_verification(
    document: ParsedDocument,
    client: CrossrefClient | None = None,
) -> ReviewResult:
    """F1 (matching) + F3 (DOI link opens). Skips F3 gracefully when disabled."""
    settings = get_settings()
    report, csl_items, llm_used = await _f1_with_optional_llm(document)
    verified: dict[str, VerifiedItem] = {}

    if client is None and not settings.f3_enabled:
        patches = build_patches(document, report, csl_items, verified)
        return ReviewResult(
            match_report=report,
            csl_items=csl_items,
            verified=verified,
            patches=patches,
            llm_used=llm_used,
        )

    own_client = client is None
    try:
        cr = client or CrossrefClient()
        if own_client:
            await cr.__aenter__()
        try:
            verified = await verify_references(csl_items, cr)
        finally:
            if own_client:
                await cr.__aexit__(None, None, None)
    except Exception as exc:  # noqa: BLE001 - F3 is best-effort
        verified = {c.id: _verification_failure_item(c, exc) for c in csl_items}

    patches = build_patches(document, report, csl_items, verified)
    return ReviewResult(
        match_report=report,
        csl_items=csl_items,
        verified=verified,
        patches=patches,
        llm_used=llm_used,
    )
