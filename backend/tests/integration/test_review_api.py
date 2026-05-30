import io
import zipfile

from docx import Document
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_docx(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_post_jobs_returns_match_report() -> None:
    data = _make_docx(
        [
            "본 연구는 선행연구 (Kim, 2023)와 (Lee & Park, 2024)를 검토한다.",
            "또한 누락된 인용 (Ghost, 2099)도 포함한다.",
            "References",
            "Kim, S. (2023). First study. Journal A, 1(1), 1-10.",
            "Lee, J., & Park, H. (2024). Second study. Journal B, 2(2), 11-20.",
            "Unused, A. (2000). Never cited. Journal C, 3(3), 21-30.",
        ]
    )
    resp = client.post(
        "/jobs",
        files={
            "file": (
                "sample.docx",
                data,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["original_format"] == "docx"
    report = body["match_report"]
    types = {i["type"] for i in report["issues"]}
    assert "orphan_citation" in types  # (Ghost, 2099)
    assert "orphan_reference" in types  # Unused (2000)
    assert report["stats"]["references"] == 3


def test_unsupported_format_returns_415() -> None:
    resp = client.post(
        "/jobs",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert resp.status_code == 415


def test_empty_file_returns_400() -> None:
    resp = client.post("/jobs", files={"file": ("x.docx", b"", "application/octet-stream")})
    assert resp.status_code == 400


def test_post_jobs_accepts_hwpx_zip_xml_fallback() -> None:
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

    resp = client.post(
        "/jobs",
        files={"file": ("sample.hwpx", buf.getvalue(), "application/octet-stream")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["original_format"] == "hwpx"
    assert body["match_report"]["stats"]["references"] == 1
