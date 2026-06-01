"""Document-level citation/reference style detection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.citation.extractor import InTextCitation
from app.citation.references import ReferenceItem

CitationSystem = Literal["apa", "ieee", "mixed", "unknown"]


class CitationStyleProfile(BaseModel):
    system: CitationSystem = "unknown"
    confidence: float = 0.0
    citation_style_counts: dict[str, int] = Field(default_factory=dict)
    reference_style_counts: dict[str, int] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)


def detect_citation_style(
    citations: list[InTextCitation],
    references: list[ReferenceItem],
) -> CitationStyleProfile:
    citation_counts: dict[str, int] = {}
    for citation in citations:
        citation_counts[citation.style] = citation_counts.get(citation.style, 0) + 1

    reference_counts = {
        "numbered": sum(1 for ref in references if ref.number is not None),
        "author_year": sum(
            1 for ref in references if ref.number is None and ref.authors and ref.year
        ),
        "unknown": sum(1 for ref in references if not ref.authors and ref.year is None),
    }

    numeric_citations = citation_counts.get("numeric", 0)
    author_year_citations = sum(
        count for style, count in citation_counts.items() if style != "numeric"
    )
    numbered_refs = reference_counts["numbered"]
    author_year_refs = reference_counts["author_year"]

    ieee_score = numeric_citations + numbered_refs
    apa_score = author_year_citations + author_year_refs
    total = ieee_score + apa_score
    evidence: list[str] = [
        f"numeric citations: {numeric_citations}",
        f"author-year citations: {author_year_citations}",
        f"numbered references: {numbered_refs}",
        f"author-year references: {author_year_refs}",
    ]

    if total == 0:
        return CitationStyleProfile(
            citation_style_counts=citation_counts,
            reference_style_counts=reference_counts,
            evidence=evidence,
        )

    high = max(ieee_score, apa_score)
    confidence = high / total
    if ieee_score and apa_score and confidence < 0.75:
        system: CitationSystem = "mixed"
    elif ieee_score > apa_score:
        system = "ieee"
    else:
        system = "apa"

    return CitationStyleProfile(
        system=system,
        confidence=round(confidence, 2),
        citation_style_counts=citation_counts,
        reference_style_counts=reference_counts,
        evidence=evidence,
    )
