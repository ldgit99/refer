"""In-text citation extraction (research.md §3.1).

Four citation styles are recognised:
  * author_year         — (Kim, 2023), (Lee & Park, 2024a)
  * korean_author_year  — (이동국, 2024), (김철수, 이영희, 2023)
  * numeric             — [12], [3, 5-7]
  * narrative           — Smith (2020) reported ...

Each citation keeps its paragraph index and character range so the UI can jump
back to the exact location.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.parsers.base import ParsedDocument

CitationStyle = Literal["author_year", "korean_author_year", "numeric", "narrative"]

# Latin author-year inside parentheses, e.g. "(Kim, 2023)", "(Lee & Park, 2024a)".
_AUTHOR_YEAR_RE = re.compile(
    r"\(([A-Z][A-Za-z.''\-]+(?:(?:,|\s|&|and|et al\.?)+[A-Za-z.''\-]+)*?)[,\s]+(\d{4})([a-z])?\)"
)
# Korean author-year, e.g. "(이동국, 2024)", "(김철수, 이영희, 2023)".
_KOREAN_AUTHOR_YEAR_RE = re.compile(
    r"\(([가-힣]{2,4}(?:\s*[,·]\s*[가-힣]{2,4})*(?:\s*외)?)[\s,]+(\d{4})([a-z])?\)"
)
# Numeric / IEEE, e.g. "[12]", "[3, 5-7]".
_NUMERIC_RE = re.compile(r"\[(\d+(?:\s*[\-,]\s*\d+)*)\]")
# Narrative, e.g. "Smith (2020)", "Kim and Lee (2019)".
_NARRATIVE_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+(?:and|&|et al\.?)\s+[A-Z][a-z]+)*)\s+\((\d{4})([a-z])?\)"
)

_KOREAN_NARRATIVE_RE = re.compile(r"([가-힣]{2,4}(?:\s*외)?)\s*\((\d{4})([a-z])?\)")


class InTextCitation(BaseModel):
    raw: str
    style: CitationStyle
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    suffix: str | None = None  # disambiguator like "a" in 2024a
    numbers: list[int] = Field(default_factory=list)
    paragraph_index: int
    char_start: int
    char_end: int


def _split_authors(group: str) -> list[str]:
    """Split a citation author group into individual family-name tokens."""
    cleaned = re.sub(r"\bet al\.?\b", "", group, flags=re.IGNORECASE)
    parts = re.split(r"\s*(?:,|&|·|and|외)\s*", cleaned)
    return [p.strip(" .'-") for p in parts if p.strip(" .'-")]


def _expand_numbers(group: str) -> list[int]:
    nums: list[int] = []
    for token in re.split(r"\s*,\s*", group):
        token = token.strip()
        if "-" in token:
            try:
                lo, hi = (int(x) for x in token.split("-", 1))
                nums.extend(range(lo, hi + 1))
            except ValueError:
                continue
        elif token.isdigit():
            nums.append(int(token))
    return nums


def _has_et_al(group: str) -> bool:
    return bool(re.search(r"et al\.?|외", group, flags=re.IGNORECASE))


def extract_from_text(text: str, paragraph_index: int) -> list[InTextCitation]:
    """Extract every in-text citation from a single paragraph's text."""
    found: list[InTextCitation] = []
    seen_spans: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(s < end and start < e for s, e in seen_spans)

    def add(cit: InTextCitation, span: tuple[int, int]) -> None:
        found.append(cit)
        seen_spans.append(span)

    for m in _AUTHOR_YEAR_RE.finditer(text):
        add(
            InTextCitation(
                raw=m.group(0),
                style="author_year",
                authors=_split_authors(m.group(1)),
                year=int(m.group(2)),
                suffix=m.group(3),
                paragraph_index=paragraph_index,
                char_start=m.start(),
                char_end=m.end(),
            ),
            (m.start(), m.end()),
        )

    for m in _KOREAN_AUTHOR_YEAR_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        add(
            InTextCitation(
                raw=m.group(0),
                style="korean_author_year",
                authors=_split_authors(m.group(1)),
                year=int(m.group(2)),
                suffix=m.group(3),
                paragraph_index=paragraph_index,
                char_start=m.start(),
                char_end=m.end(),
            ),
            (m.start(), m.end()),
        )

    for m in _NUMERIC_RE.finditer(text):
        add(
            InTextCitation(
                raw=m.group(0),
                style="numeric",
                numbers=_expand_numbers(m.group(1)),
                paragraph_index=paragraph_index,
                char_start=m.start(),
                char_end=m.end(),
            ),
            (m.start(), m.end()),
        )

    for regex in (_NARRATIVE_RE, _KOREAN_NARRATIVE_RE):
        for m in regex.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            add(
                InTextCitation(
                    raw=m.group(0),
                    style="narrative",
                    authors=_split_authors(m.group(1)),
                    year=int(m.group(2)),
                    suffix=m.group(3),
                    paragraph_index=paragraph_index,
                    char_start=m.start(),
                    char_end=m.end(),
                ),
                (m.start(), m.end()),
            )

    found.sort(key=lambda c: c.char_start)
    return found


def extract_citations(document: ParsedDocument) -> list[InTextCitation]:
    """Extract citations from all non-reference paragraphs of a document."""
    citations: list[InTextCitation] = []
    for para in document.body_paragraphs():
        citations.extend(extract_from_text(para.text, para.index))
    return citations
