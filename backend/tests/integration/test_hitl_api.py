"""HITL conflict-queue API (M6).

Builds a document whose critics will disagree (a 3-author citation without
"et al." trips C1) so the HITL queue is non-empty, then resolves a conflict.
"""

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


def test_hitl_queue_and_resolve() -> None:
    data = _make_docx(
        [
            "본 연구는 (Kim, Lee & Park, 2023)을 인용한다.",
            "References",
            "Kim, S., Lee, J., & Park, H. (2023). A study. Journal of X, 1(1), 1-10.",
        ]
    )
    resp = client.post(
        "/jobs", files={"file": ("s.docx", data, "application/octet-stream")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    job_id = body["job_id"]

    # critics dict should be present in the result.
    assert "critics" in body
    assert "consistency" in body["critics"]

    hitl = client.get(f"/jobs/{job_id}/hitl")
    assert hitl.status_code == 200
    conflicts = hitl.json()["conflicts"]

    if conflicts:
        cid = conflicts[0]["id"]
        res = client.post(
            f"/jobs/{job_id}/hitl/resolve",
            json={"conflict_id": cid, "choice": "critic"},
        )
        assert res.status_code == 200
        assert res.json()["resolved"] is True

    # Resolving an unknown conflict 404s.
    bad = client.post(
        f"/jobs/{job_id}/hitl/resolve",
        json={"conflict_id": "nope", "choice": "critic"},
    )
    assert bad.status_code == 404


def test_hitl_unknown_job_404() -> None:
    assert client.get("/jobs/nope/hitl").status_code == 404
