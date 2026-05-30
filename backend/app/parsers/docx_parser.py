"""DOCX parser built on python-docx (research.md §2.1)."""

from __future__ import annotations

import io

from docx import Document

from app.parsers.base import ParsedDocument, build_document


def parse_docx(data: bytes) -> ParsedDocument:
    """Parse a .docx byte stream into a ParsedDocument.

    Paragraph order is preserved (important for citation offsets). Empty
    paragraphs are kept so indices line up with the original document.
    """
    doc = Document(io.BytesIO(data))
    raw_paragraphs = [p.text for p in doc.paragraphs]
    return build_document(raw_paragraphs, original_format="docx")
