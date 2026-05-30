"""Format detection + parser dispatch.

DOCX is always supported. HWPX/HWP are supported when the jkf87/hwpx-skill
submodule is initialised (backend/vendor/hwpx-skill); otherwise a clear,
actionable error is returned to the client.
"""

from __future__ import annotations

from app.citation.extractor import extract_citations
from app.citation.matcher import MatchReport, match
from app.citation.references import parse_references
from app.parsers.base import ParsedDocument
from app.parsers.docx_parser import parse_docx

SUPPORTED_EXTENSIONS = {"docx", "hwpx", "hwp"}


class UnsupportedFormatError(ValueError):
    pass


def detect_format(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def parse_file(data: bytes, filename: str) -> ParsedDocument:
    ext = detect_format(filename)
    if ext == "docx":
        return parse_docx(data)
    if ext == "hwpx":
        from app.parsers.hwpx_parser import parse_hwpx

        return parse_hwpx(data)
    if ext == "hwp":
        from app.parsers.hwp_parser import parse_hwp

        return parse_hwp(data)
    raise UnsupportedFormatError(
        f"'{ext}' 포맷은 지원하지 않습니다 (지원: {', '.join(sorted(SUPPORTED_EXTENSIONS))})."
    )


def review_document(document: ParsedDocument) -> MatchReport:
    """F1-only review (kept for the M1 regression baseline)."""
    citations = extract_citations(document)
    references = parse_references(document.references_section)
    return match(citations, references)


def review_file(data: bytes, filename: str) -> MatchReport:
    return review_document(parse_file(data, filename))
