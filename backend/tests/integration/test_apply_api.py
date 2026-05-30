"""End-to-end apply flow: upload -> review -> apply -> download (F3 disabled)."""

import io

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


def _upload() -> dict:
    data = _make_docx(
        [
            "본 연구는 (Kim, 2023)를 검토한다.",
            "References",
            "Kim, S. (2023). A study. Journal of X, 1(1), 1-10.",
        ]
    )
    resp = client.post(
        "/jobs",
        files={"file": ("sample.docx", data, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_full_apply_download_cycle() -> None:
    body = _upload()
    job_id = body["job_id"]
    assert job_id

    got = client.get(f"/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["job_id"] == job_id

    patch_ids = [p["id"] for p in body["patches"]]
    apply = client.post(
        f"/jobs/{job_id}/apply",
        json={"accepted_patch_ids": patch_ids, "mode": "annotated"},
    )
    assert apply.status_code == 200, apply.text
    assert apply.json()["applied"] == len(patch_ids)

    dl = client.get(f"/jobs/{job_id}/download")
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # docx is a zip


def test_apply_none_downloads_original() -> None:
    body = _upload()
    job_id = body["job_id"]
    apply = client.post(
        f"/jobs/{job_id}/apply",
        json={"accepted_patch_ids": [], "mode": "tracked"},
    )
    assert apply.status_code == 200
    assert apply.json()["applied"] == 0
    dl = client.get(f"/jobs/{job_id}/download")
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"


def test_unknown_job_404() -> None:
    assert client.get("/jobs/deadbeef").status_code == 404
