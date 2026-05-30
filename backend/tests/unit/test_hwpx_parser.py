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
