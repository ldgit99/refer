import io
import zipfile

from app.parsers.hwpx_parser import parse_hwpx


def _minimal_hwpx(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Contents/section0.xml", f"<root><hp:t>{text}</hp:t></root>")
    return buf.getvalue()


def test_hwpx_zip_fallback_extracts_text() -> None:
    doc = parse_hwpx(_minimal_hwpx("Body text\nReferences\nKim, S. (2024). Title."))
    assert "Body text" in doc.full_text
    assert doc.original_format == "hwpx"


def test_hwpx_zip_fallback_handles_namespaced_paragraphs() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
      <hp:p><hp:run><hp:t>본문 (Kim, 2024).</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>References</hp:t></hp:run></hp:p>
      <hp:p><hp:run><hp:t>Kim, S. (2024). A study. Journal, 1(1), 1-2.</hp:t></hp:run></hp:p>
    </hp:sec>
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Contents/section0.xml", xml)

    doc = parse_hwpx(buf.getvalue())

    assert doc.references_section is not None
    assert "A study" in doc.references_section
    assert doc.body_paragraphs()[0].text == "본문 (Kim, 2024)."
