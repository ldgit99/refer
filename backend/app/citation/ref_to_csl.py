"""Deterministic reference-string -> CSLItem parser (M2).

Handles the common APA/journal shapes well enough for F2 formatting and F3
verification. Ambiguous Korean/mixed entries get a low-confidence parse that the
M3 ReferenceParserAgent (LLM fallback) can later improve.
"""

from __future__ import annotations

import re

from app.citation.csl import CSLItem, CSLName
from app.citation.references import ReferenceItem
from app.verifier.verify import extract_doi

_YEAR_RE = re.compile(r"\(?((?:19|20)\d{2})[a-z]?\)?")
_VOL_ISSUE_PAGE_RE = re.compile(
    r"(?P<vol>\d+)\s*(?:\((?P<issue>[^)]+)\))?\s*,\s*"
    r"(?P<page>[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?)"
)
_LATIN_AUTHOR_RE = re.compile(r"([A-Z][a-zA-Z'’\-]+),\s*((?:[A-Z]\.\s*)+(?:[-&]\s*)?)")


def _parse_latin_authors(segment: str) -> list[CSLName]:
    names: list[CSLName] = []
    for m in _LATIN_AUTHOR_RE.finditer(segment):
        family = m.group(1)
        given = m.group(2).strip().rstrip("&").strip()
        names.append(CSLName(family=family, given=given))
    return names


def _parse_korean_authors(segment: str) -> list[CSLName]:
    head = segment.split("(", 1)[0]
    tokens = re.findall(r"[가-힣]{2,4}", head)
    return [CSLName(family=t) for t in tokens]


def reference_to_csl(item: ReferenceItem) -> CSLItem:
    raw = item.raw
    doi = extract_doi(raw)
    year = item.year

    year_match = _YEAR_RE.search(raw)
    author_seg = raw[: year_match.start()] if year_match else raw
    rest = raw[year_match.end() :] if year_match else ""

    authors = _parse_latin_authors(author_seg)
    if not authors:
        authors = _parse_korean_authors(author_seg)

    rest = rest.lstrip(" .)")
    title = ""
    container = ""
    volume = issue = page = ""

    if rest:
        rest_clean = re.sub(r"https?://\S+", "", rest).strip()
        parts = [p.strip() for p in rest_clean.split(".") if p.strip()]
        if parts:
            title = parts[0]
        if len(parts) > 1:
            container_chunk = parts[1]
            vip = _VOL_ISSUE_PAGE_RE.search(container_chunk)
            if vip:
                container = container_chunk[: vip.start()].strip().rstrip(",")
                volume = vip.group("vol") or ""
                issue = vip.group("issue") or ""
                page = (vip.group("page") or "").replace(" ", "")
            else:
                container = container_chunk.strip()

    return CSLItem(
        id=f"ref-{item.index}",
        type="article-journal" if container else "book",
        author=authors,
        issued_year=year,
        title=title,
        container_title=container,
        volume=volume,
        issue=issue,
        page=page,
        doi=doi or "",
    )
