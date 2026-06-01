"""Reference-list parsing into lightweight reference items.

This is the deterministic fallback used in M1. The richer CSL-JSON extraction
(GROBID / LLM) arrives with the ReferenceParserAgent in M3.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

_NUMBERED_PREFIX_RE = re.compile(r"^\s*\[?(\d+)\]?[.)]?\s+")
_YEAR_RE = re.compile(r"\(?((?:19|20)\d{2})([a-z])?\)?")
_DOI_RE = re.compile(r"10\.\d{4,9}/", re.IGNORECASE)
# "Kim, S.", "Lee, J.-H.", "van Dijk, T." style family names.
_LATIN_FAMILY_RE = re.compile(r"\b([A-Z][a-zA-Z'\u2019\-]+),\s*(?:[A-Z]\.?\s*)+")
_ORG_AUTHOR_RE = re.compile(r"^\s*([A-Z][A-Za-z&.,'\u2019\- ]{3,100}?)\.?\s*\(")
_ORG_YEAR_RE = re.compile(r"^\s*[A-Z][A-Za-z&.,'\u2019\- ]{3,100}\.?\s*\((?:19|20)\d{2}[a-z]?\)")
# Korean author tokens at the start of an entry.
_KOREAN_FAMILY_RE = re.compile(r"[\uac00-\ud7a3]{2,4}")


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
    org = _ORG_AUTHOR_RE.match(text)
    if org:
        author = org.group(1).strip().rstrip(".")
        if author:
            return [author]
    # Korean: take family-name tokens appearing before the year.
    head = text.split("(", 1)[0]
    korean = _KOREAN_FAMILY_RE.findall(head)
    return korean


def _starts_reference_entry(text: str) -> bool:
    """Return true only for lines that look like the first line of a ref."""
    stripped = text.strip()
    if len(stripped) < 12:
        return False
    number_match = _NUMBERED_PREFIX_RE.match(stripped)
    if number_match:
        body = _NUMBERED_PREFIX_RE.sub("", stripped, count=1)
        return _numbered_body_looks_like_reference(body)

    year = _YEAR_RE.search(stripped)
    if not year:
        return False
    # Continuation lines can contain older years in titles or publisher names.
    if year.start() > 140:
        return False

    if _LATIN_FAMILY_RE.search(stripped[: year.start() + 1]):
        return True
    if _ORG_YEAR_RE.match(stripped):
        return True

    head = stripped[: year.start()]
    return bool(_KOREAN_FAMILY_RE.search(head))


def _numbered_body_looks_like_reference(text: str) -> bool:
    body = text.strip()
    if len(body) < 8:
        return False
    if _DOI_RE.search(body):
        return True
    year = _YEAR_RE.search(body)
    if not year:
        return False
    return bool(
        _LATIN_FAMILY_RE.search(body[: year.start() + 1])
        or _ORG_YEAR_RE.match(body)
        or _KOREAN_FAMILY_RE.search(body[: year.start()])
    )


def _looks_like_reference_entry(text: str) -> bool:
    """Filter out section headings/body fragments inside a detected ref block."""
    stripped = text.strip()
    if len(stripped) < 12:
        return False
    number_match = _NUMBERED_PREFIX_RE.match(stripped)
    if number_match:
        body = _NUMBERED_PREFIX_RE.sub("", stripped, count=1)
        return _numbered_body_looks_like_reference(body)
    if _DOI_RE.search(stripped):
        return True
    if not _YEAR_RE.search(stripped):
        return False
    if _LATIN_FAMILY_RE.search(stripped) or _ORG_YEAR_RE.match(stripped):
        return True
    head = stripped.split("(", 1)[0]
    return bool(_KOREAN_FAMILY_RE.search(head))


def _looks_like_section_fragment(text: str) -> bool:
    stripped = text.strip()
    if _YEAR_RE.search(stripped) or _DOI_RE.search(stripped):
        return False
    if len(stripped) > 30:
        return False
    return bool(re.match(r"^[\uac00-\ud7a3A-Za-z0-9]{1,4}[.)]\s+\S+", stripped))


def _looks_like_body_prose(text: str) -> bool:
    stripped = text.strip()
    if _DOI_RE.search(stripped):
        return False
    korean_chars = len(re.findall(r"[\uac00-\ud7a3]", stripped))
    if korean_chars < 20 or len(stripped) < 80:
        return False
    sentence_endings = len(re.findall(r"(?:다|요|음|함|됨|임)\.", stripped))
    return sentence_endings >= 2


def _split_entries(section: str) -> list[str]:
    """Split a reference block into individual entries.

    Numbered styles split on the leading "[n]"/"n." prefix; otherwise each
    entry-start line opens a record and wrapped HWPX paragraphs are merged into
    the previous entry.
    """
    lines = [ln.rstrip() for ln in section.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return []

    numbered_refs = 0
    for ln in lines:
        if _NUMBERED_PREFIX_RE.match(ln):
            body = _NUMBERED_PREFIX_RE.sub("", ln.strip(), count=1)
            if _numbered_body_looks_like_reference(body):
                numbered_refs += 1
    first_numbered = _NUMBERED_PREFIX_RE.match(lines[0])
    first_numbered_ref = False
    if first_numbered:
        first_body = _NUMBERED_PREFIX_RE.sub("", lines[0].strip(), count=1)
        first_numbered_ref = _numbered_body_looks_like_reference(first_body)
    if numbered_refs >= 2 or first_numbered_ref:
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

    entries: list[str] = []
    current: str | None = None
    for ln in lines:
        stripped = ln.strip()
        if _starts_reference_entry(stripped):
            if current:
                entries.append(current)
            current = stripped
        elif (
            current
            and not _looks_like_section_fragment(stripped)
            and not _looks_like_body_prose(stripped)
        ):
            current += " " + stripped
    if current:
        entries.append(current)
    return entries


def parse_references(section: str | None) -> list[ReferenceItem]:
    if not section:
        return []
    items: list[ReferenceItem] = []
    entries = [raw for raw in _split_entries(section) if _looks_like_reference_entry(raw)]
    for idx, raw in enumerate(entries):
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
