"""HTTP routes.

M1 is intentionally synchronous: ``POST /jobs`` parses + matches in-request and
returns the report as JSON. The async job/queue/SSE surface arrives in M2.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import JobResult
from app.pipeline import UnsupportedFormatError, parse_file, review_document

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/jobs", response_model=JobResult, tags=["review"])
async def create_job(file: Annotated[UploadFile, File()]) -> JobResult:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 25MB).")

    filename = file.filename or "upload"
    try:
        document = parse_file(data, filename)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface parse failures to the client
        raise HTTPException(status_code=422, detail=f"문서 파싱 실패: {exc}") from exc

    report = review_document(document)
    return JobResult(
        filename=filename,
        original_format=document.original_format,
        match_report=report,
    )
