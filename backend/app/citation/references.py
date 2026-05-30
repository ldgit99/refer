"""Reference-list parsing into lightweight reference items (research.md §2.4).

This is the deterministic fallback used in M1. The richer CSL-JSON extraction
(GROBID / LLM) arrives with the ReferenceParserAgent in M3.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

_NUMBERED_PREFIX_RE = re.compile(r"^\s*\[?(\d+)\]?[.)]?\s+")
_YEAR_RE = re.compile(r"\(?((?:19|20)\d{2})([a-z])?\)?")
# "Kim, S.", "Lee, J.-H.", "van Dijk, T." style family names.
_LATIN_FAMILY_RE = re.compile(r"\b([A-Z][a-zA-Z'’\-]+),\s*(?:[A-Z]\.?\s*)+")
# Korean author tokens at the start of an entry.
_KOREAN_FAMILY_RE = re.compile(r"[가-힣]{2,4}")


class ReferenceItem(BaseModel):
    index: int
    raw: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    suffix: str | None = None
    number: int | None = None  # explicit [n] for numbered styles


def _extract_year(text: str) -> tuple[int | None, str | None]:
    m = _YEAR_RE.search(text)
    if not m:
        return None, None
    return int(m.group(1)), m.group(2)


def _extract_authors(text: str) -> list[str]:
    families = [m.group(1) for m in _LATIN_FAMILY_RE.finditer(text)]
    if families:
        return families
    # Korean: take family-name tokens appearing before the year.
    head = text.split("(", 1)[0]
    korean = _KOREAN_FAMILY_RE.findall(head)
    return korean


def _split_entries(section: str) -> list[str]:
    """Split a reference block into individual entries.

    Numbered styles split on the leading "[n]"/"n." prefix; otherwise each
    non-empty line (hanging indent) is treated as one entry.
    """
    lines = [ln.rstrip() for ln in section.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return []

    numbered = sum(1 for ln in lines if _NUMBERED_PREFIX_RE.match(ln))
    if numbered >= max(2, len(lines) // 2):
        # Merge wrapped continuation lines into their numbered entry.
        entries: list[str] = []
        for ln in lines:
            if _NUMBERED_PREFIX_RE.match(ln):
                entries.append(ln)
            elif entries:
                entries[-1] += " " + ln.strip()
            else:
                entries.append(ln)
        return entries
    return lines


def parse_references(section: str | None) -> list[ReferenceItem]:
    if not section:
        return []
    items: list[ReferenceItem] = []
    for idx, raw in enumerate(_split_entries(section)):
        number_match = _NUMBERED_PREFIX_RE.match(raw)
        number = int(number_match.group(1)) if number_match else None
        body = _NUMBERED_PREFIX_RE.sub("", raw) if number_match else raw
        year, suffix = _extract_year(body)
        items.append(
            ReferenceItem(
                index=idx,
                raw=raw.strip(),
                authors=_extract_authors(body),
                year=year,
                suffix=suffix,
                number=number,
            )
        )
    return items
