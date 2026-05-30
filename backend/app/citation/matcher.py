"""F1 — deterministic citation ↔ reference matching (research.md §3.2).

Produces four issue types:
  * orphan_citation        — cited in text but missing from the reference list
  * orphan_reference       — listed but never cited
  * year_mismatch          — author matches but the year differs
  * author_count_mismatch  — APA 7 "et al." rule violation (3+ authors)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from app.citation.extractor import InTextCitation
from app.citation.references import ReferenceItem
from app.config import get_settings

IssueType = Literal[
    "orphan_citation",
    "orphan_reference",
    "year_mismatch",
    "author_count_mismatch",
]
Severity = Literal["INFO", "WARNING", "CRITICAL"]


class MatchIssue(BaseModel):
    type: IssueType
    severity: Severity
    message: str
    citation_raw: str | None = None
    reference_raw: str | None = None
    paragraph_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    reference_index: int | None = None


class MatchReport(BaseModel):
    citations: list[InTextCitation] = Field(default_factory=list)
    references: list[ReferenceItem] = Field(default_factory=list)
    issues: list[MatchIssue] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


def _norm(name: str) -> str:
    return name.lower().strip(" .,'’-")


def _author_similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(_norm(a), _norm(b)) / 100.0


def _first_author_matches(cit: InTextCitation, ref: ReferenceItem, threshold: float) -> bool:
    if not cit.authors or not ref.authors:
        return False
    return _author_similarity(cit.authors[0], ref.authors[0]) >= threshold


def match(
    citations: list[InTextCitation],
    references: list[ReferenceItem],
) -> MatchReport:
    settings = get_settings()
    threshold = settings.fuzzy_match_threshold
    issues: list[MatchIssue] = []

    matched_reference_indices: set[int] = set()

    numeric_citations = [c for c in citations if c.style == "numeric"]
    name_citations = [c for c in citations if c.style != "numeric"]

    # --- numeric style: [n] maps directly to reference number / position ---
    ref_by_number: dict[int, ReferenceItem] = {}
    for ref in references:
        key = ref.number if ref.number is not None else ref.index + 1
        ref_by_number[key] = ref

    for cit in numeric_citations:
        for n in cit.numbers:
            ref = ref_by_number.get(n)
            if ref is None:
                issues.append(
                    MatchIssue(
                        type="orphan_citation",
                        severity="CRITICAL",
                        message=f"본문 인용 [{n}]에 해당하는 참고문헌 항목이 없습니다.",
                        citation_raw=cit.raw,
                        paragraph_index=cit.paragraph_index,
                        char_start=cit.char_start,
                        char_end=cit.char_end,
                    )
                )
            else:
                matched_reference_indices.add(ref.index)

    # --- author-year styles ---
    for cit in name_citations:
        candidates = [
            ref
            for ref in references
            if _first_author_matches(cit, ref, threshold)
        ]
        if not candidates:
            issues.append(
                MatchIssue(
                    type="orphan_citation",
                    severity="CRITICAL",
                    message=f"본문 인용 {cit.raw!r}에 매칭되는 참고문헌이 없습니다.",
                    citation_raw=cit.raw,
                    paragraph_index=cit.paragraph_index,
                    char_start=cit.char_start,
                    char_end=cit.char_end,
                )
            )
            continue

        year_match = [r for r in candidates if cit.year is not None and r.year == cit.year]
        chosen = year_match[0] if year_match else candidates[0]
        matched_reference_indices.add(chosen.index)

        if not year_match and cit.year is not None and chosen.year is not None:
            issues.append(
                MatchIssue(
                    type="year_mismatch",
                    severity="WARNING",
                    message=(
                        f"본문 {cit.raw!r}의 연도({cit.year})와 참고문헌 연도"
                        f"({chosen.year})가 다릅니다."
                    ),
                    citation_raw=cit.raw,
                    reference_raw=chosen.raw,
                    paragraph_index=cit.paragraph_index,
                    char_start=cit.char_start,
                    char_end=cit.char_end,
                    reference_index=chosen.index,
                )
            )

        # APA 7: 3+ authors must use "et al." from the first citation.
        has_et_al = "외" in cit.raw or "et al" in cit.raw.lower()
        if len(chosen.authors) >= 3 and len(cit.authors) >= 3 and not has_et_al:
            issues.append(
                MatchIssue(
                    type="author_count_mismatch",
                    severity="WARNING",
                    message=(
                        f"저자 3인 이상 문헌은 APA 7판에서 첫 인용부터 'et al.'을 "
                        f"사용해야 합니다: {cit.raw!r}"
                    ),
                    citation_raw=cit.raw,
                    reference_raw=chosen.raw,
                    paragraph_index=cit.paragraph_index,
                    char_start=cit.char_start,
                    char_end=cit.char_end,
                    reference_index=chosen.index,
                )
            )

    # --- orphan references (listed but never cited) ---
    for ref in references:
        if ref.index not in matched_reference_indices:
            issues.append(
                MatchIssue(
                    type="orphan_reference",
                    severity="WARNING",
                    message=f"참고문헌 항목이 본문에서 인용되지 않았습니다: {ref.raw[:60]!r}",
                    reference_raw=ref.raw,
                    reference_index=ref.index,
                )
            )

    stats = {
        "citations": len(citations),
        "references": len(references),
        "issues": len(issues),
        "orphan_citation": sum(1 for i in issues if i.type == "orphan_citation"),
        "orphan_reference": sum(1 for i in issues if i.type == "orphan_reference"),
        "year_mismatch": sum(1 for i in issues if i.type == "year_mismatch"),
        "author_count_mismatch": sum(
            1 for i in issues if i.type == "author_count_mismatch"
        ),
    }

    return MatchReport(
        citations=citations,
        references=references,
        issues=issues,
        stats=stats,
    )
