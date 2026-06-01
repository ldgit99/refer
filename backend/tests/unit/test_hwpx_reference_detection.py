import io
import zipfile

from app.parsers.hwpx_parser import parse_hwpx


def _hwpx_from_paragraphs(paragraphs: list[str]) -> bytes:
    xml_paragraphs = "\n".join(
        f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>" for text in paragraphs
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
      {xml_paragraphs}
    </hp:sec>
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Contents/section0.xml", xml)
    return buf.getvalue()


def test_hwpx_detects_decorated_korean_reference_heading() -> None:
    doc = parse_hwpx(
        _hwpx_from_paragraphs(
            [
                "본문 (Kasneci et al., 2023).",
                "Ⅴ. 참 고 문 헌",
                "Kasneci, E., Sessler, K., & Küchemann, S. (2023). ChatGPT for good? Learning and Individual Differences, 103, 102274. https://doi.org/10.1016/j.lindif.2023.102274",
            ]
        )
    )

    assert doc.references_section is not None
    assert "Kasneci" in doc.references_section


def test_hwpx_infers_headingless_reference_list() -> None:
    doc = parse_hwpx(
        _hwpx_from_paragraphs(
            [
                "본문 (Kasneci et al., 2023; Hattie & Timperley, 2007).",
                "Kasneci, E., Sessler, K., & Küchemann, S. (2023). ChatGPT for good? Learning and Individual Differences, 103, 102274. https://doi.org/10.1016/j.lindif.2023.102274",
                "Hattie, J., & Timperley, H. (2007). The power of feedback. Review of Educational Research, 77(1), 81-112. https://doi.org/10.3102/003465430298487",
            ]
        )
    )

    assert doc.references_section is not None
    assert "Kasneci" in doc.references_section
    assert "Hattie" in doc.references_section
