"""Common parsed-document schema shared by every format parser.

Offsets are preserved so the frontend can jump from an issue back to the exact
paragraph + character range in the original document (research.md §12.5).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Heading that marks the start of the reference section (research.md §2.4).
REFERENCE_HEADING_RE = re.compile(
    r"^\s*(참고\s*문헌|references|reference|bibliography|works\s+cited|인용\s*문헌)\s*$",
    re.IGNORECASE,
)


# HWPX extractors often preserve decorative spacing/numbering, e.g.
# "참 고 문 헌", "Ⅴ. 참고문헌", "# References".
REFERENCE_HEADING_RE = re.compile(
    r"(참\s*고\s*문\s*헌|참\s*고\s*자\s*료|인\s*용\s*문\s*헌|"
    r"references?|bibliography|works\s+cited)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\(?((?:19|20)\d{2})([a-z])?\)?")
_DOI_RE = re.compile(r"10\.\d{4,9}/", re.IGNORECASE)
_NUMBERED_REF_RE = re.compile(r"^\s*\[?\d+\]?[.)]?\s+")
_LATIN_REF_RE = re.compile(r"^\s*[A-Z][A-Za-z'’\-]+,\s*(?:[A-Z]\.?\s*)+")
_KOREAN_REF_RE = re.compile(r"^\s*[\uAC00-\uD7A3]{2,5}\s*(?:,|·|ㆍ|&|and|\()")


def _compact_heading(text: str) -> str:
    return re.sub(r"[\s#*_=\-–—·•:：.,;()\[\]{}<>【】0-9ivxlcdmⅠ-Ⅹ]+", "", text.lower())


def is_reference_heading(text: str) -> bool:
    compact = _compact_heading(text)
    if compact.startswith(("참고문헌", "참고자료", "인용문헌")):
        return True
    return bool(REFERENCE_HEADING_RE.search(text))


def _looks_like_reference_entry(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 12 or not _YEAR_RE.search(stripped):
        return False
    if _DOI_RE.search(stripped) or _NUMBERED_REF_RE.match(stripped):
        return True
    return bool(_LATIN_REF_RE.match(stripped) or _KOREAN_REF_RE.match(stripped))


def _infer_reference_start(raw_paragraphs: list[str]) -> int | None:
    """Infer a heading-less reference list from consecutive reference-like lines."""
    if len(raw_paragraphs) < 3:
        return None
    start_at = max(1, len(raw_paragraphs) // 3)
    for idx in range(start_at, len(raw_paragraphs)):
        if not _looks_like_reference_entry(raw_paragraphs[idx]):
            continue
        window = raw_paragraphs[idx : min(len(raw_paragraphs), idx + 6)]
        ref_like = sum(1 for line in window if _looks_like_reference_entry(line))
        if ref_like >= min(2, len(window)):
            return idx
    return None


class Paragraph(BaseModel):
    """A single paragraph with its offset inside ``ParsedDocument.full_text``."""

    index: int
    text: str
    char_start: int
    char_end: int
    is_reference: bool = False


class ParsedDocument(BaseModel):
    full_text: str
    paragraphs: list[Paragraph] = Field(default_factory=list)
    references_section: str | None = None
    references_start_index: int | None = None
    original_format: str = "docx"

    def reference_paragraphs(self) -> list[Paragraph]:
        return [p for p in self.paragraphs if p.is_reference]

    def body_paragraphs(self) -> list[Paragraph]:
        return [p for p in self.paragraphs if not p.is_reference]


def build_document(
    raw_paragraphs: list[str],
    original_format: str = "docx",
) -> ParsedDocument:
    """Assemble a ParsedDocument from raw paragraph strings.

    Detects the reference heading and flags everything after it as the reference
    section, slicing it out for downstream reference parsing.
    """
    paragraphs: list[Paragraph] = []
    cursor = 0
    ref_start: int | None = None

    for idx, text in enumerate(raw_paragraphs):
        start = cursor
        end = start + len(text)
        cursor = end + 1  # +1 for the "\n" joiner

        if ref_start is None and is_reference_heading(text):
            ref_start = idx

        paragraphs.append(
            Paragraph(index=idx, text=text, char_start=start, char_end=end)
        )

    ref_content_start: int | None = None
    if ref_start is not None:
        ref_content_start = ref_start + 1
    else:
        ref_content_start = _infer_reference_start(raw_paragraphs)
        if ref_content_start is not None:
            ref_start = max(ref_content_start - 1, 0)

    references_section: str | None = None
    if ref_content_start is not None:
        for p in paragraphs[ref_content_start:]:
            p.is_reference = True
        ref_lines = [p.text for p in paragraphs[ref_content_start:] if p.text.strip()]
        references_section = "\n".join(ref_lines) or None

    full_text = "\n".join(raw_paragraphs)
    return ParsedDocument(
        full_text=full_text,
        paragraphs=paragraphs,
        references_section=references_section,
        references_start_index=ref_start,
        original_format=original_format,
    )
