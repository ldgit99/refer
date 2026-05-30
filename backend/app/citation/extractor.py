"""In-text citation extraction.

Recognised citation styles:
  * author_year: (Kim, 2023), (Lee & Park, 2024a), (Kim et al., 2024)
  * korean_author_year: (김동국, 2024), (김철수, 이영희, 2023)
  * numeric: [12], [3, 5-7]
  * narrative: Smith (2020), Kim et al. (2024), Kim, Lee, and Park (2024)

Each citation keeps its paragraph index and character range so the UI can jump
back to the exact location.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.parsers.base import ParsedDocument

CitationStyle = Literal["author_year", "korean_author_year", "numeric", "narrative"]

_LATIN_NAME = r"[A-Z][A-Za-z.''\-]+"
_KOREAN_NAME = r"[가-힣]{2,4}"

# Parenthetical Latin author-year citations. The author group is intentionally
# permissive because the splitter normalises separators and "et al." later.
_AUTHOR_YEAR_RE = re.compile(
    rf"\(([^()]*?{_LATIN_NAME}[^()]*?)[,\s]+(\d{{4}})([a-z])?\)"
)
_KOREAN_AUTHOR_YEAR_RE = re.compile(
    rf"\((({_KOREAN_NAME})(?:\s*[,·]\s*{_KOREAN_NAME})*(?:\s*(?:등|외))?)[\s,]+(\d{{4}})([a-z])?\)"
)
_NUMERIC_RE = re.compile(r"\[(\d+(?:\s*[\-,]\s*\d+)*)\]")
_NARRATIVE_RE = re.compile(
    rf"\b({_LATIN_NAME}(?:\s+et\s+al\.?|(?:\s*,\s*{_LATIN_NAME})*(?:,?\s*(?:and|&)\s*{_LATIN_NAME})?))\s+\((\d{{4}})([a-z])?\)"
)
_KOREAN_NARRATIVE_RE = re.compile(
    rf"(({_KOREAN_NAME})(?:\s*(?:등|외))?)\s*\((\d{{4}})([a-z])?\)"
)
_PAREN_GROUP_RE = re.compile(r"\(([^()]*\d{4}[a-z]?[^()]*)\)")
_AUTHOR_YEAR_PART_RE = re.compile(r"^\s*(.+?)[,\s]+(\d{4})([a-z])?\s*$")


class InTextCitation(BaseModel):
    raw: str
    style: CitationStyle
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    suffix: str | None = None
    numbers: list[int] = Field(default_factory=list)
    paragraph_index: int
    char_start: int
    char_end: int


def _split_authors(group: str) -> list[str]:
    """Split a citation author group into family-name tokens."""
    cleaned = re.sub(r"\bet\s+al\.?\b", "", group, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*(?:등|외)\b", "", cleaned)
    parts = re.split(r"\s*(?:,|·|&|and)\s*", cleaned)
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


def extract_from_text(text: str, paragraph_index: int) -> list[InTextCitation]:
    """Extract every in-text citation from a single paragraph."""
    found: list[InTextCitation] = []
    seen_spans: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(s < end and start < e for s, e in seen_spans)

    def add(cit: InTextCitation, span: tuple[int, int]) -> None:
        found.append(cit)
        seen_spans.append(span)

    for m in _PAREN_GROUP_RE.finditer(text):
        content = m.group(1)
        if ";" not in content:
            continue
        parts = [part.strip() for part in content.split(";") if part.strip()]
        parsed_parts: list[tuple[str, re.Match[str], int]] = []
        search_from = 0
        for part in parts:
            pm = _AUTHOR_YEAR_PART_RE.match(part)
            if not pm:
                parsed_parts = []
                break
            relative_start = content.find(part, search_from)
            if relative_start < 0:
                relative_start = search_from
            search_from = relative_start + len(part)
            parsed_parts.append((part, pm, relative_start))

        if not parsed_parts:
            continue

        for part, pm, relative_start in parsed_parts:
            start = m.start(1) + relative_start
            end = start + len(part)
            raw = f"({part})"
            style: CitationStyle = (
                "korean_author_year"
                if re.search(_KOREAN_NAME, pm.group(1))
                else "author_year"
            )
            add(
                InTextCitation(
                    raw=raw,
                    style=style,
                    authors=_split_authors(pm.group(1)),
                    year=int(pm.group(2)),
                    suffix=pm.group(3),
                    paragraph_index=paragraph_index,
                    char_start=start,
                    char_end=end,
                ),
                (m.start(), m.end()),
            )

    for m in _AUTHOR_YEAR_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
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
                year=int(m.group(3)),
                suffix=m.group(4),
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
                    year=int(m.group(2 if regex is _NARRATIVE_RE else 3)),
                    suffix=m.group(3 if regex is _NARRATIVE_RE else 4),
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
