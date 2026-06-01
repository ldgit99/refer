"""The DOCX writer must emit a real word/comments.xml part for citation comments."""

import io
import zipfile

from docx import Document

from app.writers.base import ParagraphRef, Patch
from app.writers.docx_writer import DocxWriter


def _docx(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_citation_comment_creates_comments_part() -> None:
    data = _docx(["본 연구는 (Ghost, 2099)를 인용한다.", "본문 계속."])
    patch = Patch(
        id="c1",
        kind="citation_comment",
        target=ParagraphRef(paragraph_index=0, char_start=6, char_end=19),
        before="(Ghost, 2099)",
        comment="[F1 orphan_citation] 매칭되는 참고문헌이 없습니다.",
        source="F1",
        severity="CRITICAL",
    )
    out = DocxWriter().apply(data, [patch], mode="annotated")

    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        names = zf.namelist()
        assert "word/comments.xml" in names
        comments_xml = zf.read("word/comments.xml").decode("utf-8")
        assert "orphan_citation" in comments_xml
        body_xml = zf.read("word/document.xml").decode("utf-8")
        assert "commentReference" in body_xml
        assert "commentRangeStart" in body_xml


def test_no_comment_part_without_citation_comments() -> None:
    data = _docx(["References", "Old, A. (2000). Old."])
    patch = Patch(
        id="r1",
        kind="reference_replace",
        target=ParagraphRef(paragraph_index=1),
        before="Old, A. (2000). Old.",
        after="New ref.",
        source="F2",
    )
    out = DocxWriter().apply(data, [patch], mode="final")
    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        assert "word/comments.xml" not in zf.namelist()
