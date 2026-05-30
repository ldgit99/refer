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

        if ref_start is None and REFERENCE_HEADING_RE.match(text):
            ref_start = idx

        paragraphs.append(
            Paragraph(index=idx, text=text, char_start=start, char_end=end)
        )

    references_section: str | None = None
    if ref_start is not None:
        # Everything after the heading paragraph is the reference block.
        for p in paragraphs[ref_start + 1 :]:
            p.is_reference = True
        ref_lines = [p.text for p in paragraphs[ref_start + 1 :] if p.text.strip()]
        references_section = "\n".join(ref_lines) or None

    full_text = "\n".join(raw_paragraphs)
    return ParsedDocument(
        full_text=full_text,
        paragraphs=paragraphs,
        references_section=references_section,
        references_start_index=ref_start,
        original_format=original_format,
    )
