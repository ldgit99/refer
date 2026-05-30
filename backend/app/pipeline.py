"""End-to-end deterministic review pipeline (M1).

parse → extract citations → parse references → F1 match.

In M3 this functional pipeline is wrapped into a LangGraph StateGraph, but the
deterministic core stays identical so the M2-vs-M3 regression test (plan.md M3)
can assert equal output.
"""

from __future__ import annotations

from app.citation.extractor import extract_citations
from app.citation.matcher import MatchReport, match
from app.citation.references import parse_references
from app.parsers.base import ParsedDocument
from app.parsers.docx_parser import parse_docx

SUPPORTED_EXTENSIONS = {"docx"}


class UnsupportedFormatError(ValueError):
    pass


def detect_format(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext


def parse_file(data: bytes, filename: str) -> ParsedDocument:
    ext = detect_format(filename)
    if ext == "docx":
        return parse_docx(data)
    raise UnsupportedFormatError(
        f"'{ext}' 포맷은 아직 지원하지 않습니다 (현재: {', '.join(sorted(SUPPORTED_EXTENSIONS))})."
    )


def review_document(document: ParsedDocument) -> MatchReport:
    citations = extract_citations(document)
    references = parse_references(document.references_section)
    return match(citations, references)


def review_file(data: bytes, filename: str) -> MatchReport:
    document = parse_file(data, filename)
    return review_document(document)
