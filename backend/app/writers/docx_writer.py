"""DOCX writer with tracked-changes / annotated output (research.md §2.5.2).

Tracked mode wraps replacements in ``w:ins``/``w:del`` runs so Word shows them
under "Track Changes". Annotated mode highlights the affected run instead.
Both modes are minimally invasive: only targeted paragraphs are touched.
"""

from __future__ import annotations

import io

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.writers.base import OutputMode, Patch

_AUTHOR = "refer"
_DATE = "2026-01-01T00:00:00Z"


def _make_run_element(text: str):
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def _make_highlight_run(text: str, color: str = "yellow"):
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    hl = OxmlElement("w:highlight")
    hl.set(qn("w:val"), color)
    rpr.append(hl)
    r.append(rpr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def _wrap_ins(run_el, rev_id: int):
    ins = OxmlElement("w:ins")
    ins.set(qn("w:id"), str(rev_id))
    ins.set(qn("w:author"), _AUTHOR)
    ins.set(qn("w:date"), _DATE)
    ins.append(run_el)
    return ins


def _wrap_del(text: str, rev_id: int):
    delel = OxmlElement("w:del")
    delel.set(qn("w:id"), str(rev_id))
    delel.set(qn("w:author"), _AUTHOR)
    delel.set(qn("w:date"), _DATE)
    r = OxmlElement("w:r")
    dtext = OxmlElement("w:delText")
    dtext.set(qn("xml:space"), "preserve")
    dtext.text = text
    r.append(dtext)
    delel.append(r)
    return delel


class DocxWriter:
    def apply(
        self,
        data: bytes,
        patches: list[Patch],
        mode: OutputMode = "tracked",
    ) -> bytes:
        doc = Document(io.BytesIO(data))
        paragraphs = doc.paragraphs
        rev = 1000

        for patch in patches:
            idx = patch.target.paragraph_index
            if idx < 0 or idx >= len(paragraphs):
                continue
            para = paragraphs[idx]

            if patch.kind in {"reference_replace", "doi_insert"}:
                rev = self._replace_paragraph(para, patch, mode, rev)
            elif patch.kind == "citation_comment":
                rev = self._annotate_paragraph(para, patch, mode, rev)

        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    def _clear_runs(self, para) -> None:
        for r in list(para.runs):
            r._element.getparent().remove(r._element)

    def _replace_paragraph(self, para, patch: Patch, mode: OutputMode, rev: int) -> int:
        original = patch.before or para.text
        new_text = patch.after
        if mode == "final":
            self._clear_runs(para)
            para.add_run(new_text)
            return rev

        p = para._p
        self._clear_runs(para)
        if mode == "tracked":
            p.append(_wrap_del(original, rev))
            rev += 1
            p.append(_wrap_ins(_make_run_element(new_text), rev))
            rev += 1
        else:  # annotated: keep original, append suggestion highlighted
            p.append(_make_run_element(original + "  "))
            p.append(_make_highlight_run(f"[제안: {new_text}]"))
        return rev

    def _annotate_paragraph(self, para, patch: Patch, mode: OutputMode, rev: int) -> int:
        note = patch.comment or patch.after or "검토 필요"
        p = para._p
        if mode == "tracked":
            p.append(_wrap_ins(_make_highlight_run(f" [{note}]"), rev))
            rev += 1
        else:
            p.append(_make_highlight_run(f" [{note}]"))
        return rev
