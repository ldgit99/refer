"""HTTP routes.

From M3 the review is driven by the LangGraph wrapper (specialists + critics +
HITL queue). ``POST /jobs`` creates a job and runs the review, ``GET /jobs/{id}``
returns the report + patch proposals + critics, ``POST /jobs/{id}/apply`` writes
the edited file (idempotent over accepted patch ids), ``GET /jobs/{id}/download``
streams it, ``/jobs/{id}/hitl[/resolve]`` drives the conflict queue (M6), and
``GET /jobs/{id}/events`` is an SSE progress stream.

The review runs in-request here (the demo is single-process). The arq/Redis
queue from plan.md M2 §6 swaps in behind this same surface without API changes.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.agents.graph import run_review_graph
from app.api.schemas import (
    ApplyRequest,
    ApplyResponse,
    HitlResolveRequest,
    HitlResolveResponse,
    HitlResponse,
    JobResult,
)
from app.pipeline import UnsupportedFormatError, detect_format, parse_file
from app.review import ReviewResult
from app.storage.files import Job, get_job_store
from app.writers.registry import get_writer

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_CRITIC_KEYS = (
    "match_report_critic",
    "formatted_critic",
    "verified_critic",
    "consistency",
)


def _job_result(job: Job) -> JobResult:
    assert job.result is not None
    return JobResult(
        job_id=job.id,
        filename=job.filename,
        original_format=job.original_format,
        status=job.status,
        match_report=job.result.match_report,
        formatted=job.result.formatted,
        verified=job.result.verified,
        patches=job.result.patches,
        critics=job.critics,
        hitl_queue=job.hitl_queue,
        llm_used=job.result.llm_used,
    )


@router.post("/jobs", response_model=JobResult, tags=["review"])
async def create_job(file: Annotated[UploadFile, File()]) -> JobResult:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 25MB).")

    filename = file.filename or "upload"
    fmt = detect_format(filename)
    try:
        document = parse_file(data, filename)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"문서 파싱 실패: {exc}") from exc

    store = get_job_store()
    job = store.create(filename=filename, original_format=fmt, data=data)
    job.status = "processing"
    store.add_event(job.id, "parsed", f"{len(document.paragraphs)} paragraphs")

    state = await run_review_graph(document)

    job.result = ReviewResult(
        match_report=state["match_report"],
        csl_items=state.get("csl_items", []),
        formatted=state.get("formatted", {}),
        verified=state.get("verified", {}),
        patches=state.get("patch_proposals", []),
        llm_used=state.get("llm_used", False),
    )
    job.critics = {k: state[k] for k in _CRITIC_KEYS if k in state}
    job.hitl_queue = state.get("hitl_queue", [])
    job.status = "done"
    store.add_event(job.id, "done", f"{len(job.result.patches)} patches")
    store.save(job)

    return _job_result(job)


@router.get("/jobs/{job_id}", response_model=JobResult, tags=["review"])
async def get_job(job_id: str) -> JobResult:
    store = get_job_store()
    job = store.get(job_id)
    if not job or job.result is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return _job_result(job)


@router.post("/jobs/{job_id}/apply", response_model=ApplyResponse, tags=["review"])
async def apply_job(job_id: str, body: ApplyRequest) -> ApplyResponse:
    store = get_job_store()
    job = store.get(job_id)
    if not job or job.result is None or job.original_bytes is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    # Idempotent: dedupe accepted ids (plan.md M6 §4, research.md §12.12).
    accepted = set(body.accepted_patch_ids)
    job.applied_patch_ids = accepted
    patches = [p for p in job.result.patches if p.id in accepted]

    try:
        writer = get_writer(job.original_format)
        edited = writer.apply(job.original_bytes, patches, body.mode)
        job.output_format = getattr(writer, "produces_format", job.original_format)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"파일 생성 실패: {exc}") from exc

    job.edited_bytes = edited
    job.status = "applied"
    store.add_event(job.id, "applied", f"{len(patches)} patches, mode={body.mode}")
    store.save(job)

    return ApplyResponse(
        job_id=job.id,
        applied=len(patches),
        download_url=f"/jobs/{job.id}/download",
    )


@router.get("/jobs/{job_id}/download", tags=["review"])
async def download_job(job_id: str) -> StreamingResponse:
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    blob = job.edited_bytes if job.edited_bytes is not None else job.original_bytes
    if blob is None:
        raise HTTPException(status_code=404, detail="다운로드할 파일이 없습니다.")
    out_fmt = job.output_format or job.original_format
    media = _DOCX_MIME if out_fmt == "docx" else "application/octet-stream"
    base = job.filename.rsplit(".", 1)[0] if "." in job.filename else job.filename
    out_name = f"reviewed_{base}.{out_fmt}"
    headers = {"Content-Disposition": f'attachment; filename="{out_name}"'}
    return StreamingResponse(io.BytesIO(blob), media_type=media, headers=headers)


@router.get("/jobs/{job_id}/hitl", response_model=HitlResponse, tags=["hitl"])
async def get_hitl(job_id: str) -> HitlResponse:
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return HitlResponse(job_id=job.id, conflicts=job.hitl_queue)


@router.post(
    "/jobs/{job_id}/hitl/resolve",
    response_model=HitlResolveResponse,
    tags=["hitl"],
)
async def resolve_hitl(job_id: str, body: HitlResolveRequest) -> HitlResolveResponse:
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    for c in job.hitl_queue:
        if c.id == body.conflict_id:
            c.resolved = True
            c.resolution = body.choice
            store.save(job)
            return HitlResolveResponse(
                job_id=job.id, conflict_id=body.conflict_id, resolved=True
            )
    raise HTTPException(status_code=404, detail="해당 충돌을 찾을 수 없습니다.")


@router.get("/jobs/{job_id}/events", tags=["review"])
async def job_events(job_id: str) -> StreamingResponse:
    store = get_job_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    async def event_gen():
        sent = 0
        for _ in range(60):  # cap the stream lifetime for the demo
            current = store.get(job_id)
            if current is None:
                break
            while sent < len(current.events):
                ev = current.events[sent]
                sent += 1
                yield f"event: progress\ndata: {json.dumps(ev)}\n\n"
            if current.status in {"done", "applied", "error"}:
                payload = json.dumps({"status": current.status})
                yield f"event: {current.status}\ndata: {payload}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
