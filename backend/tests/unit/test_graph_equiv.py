"""M2-vs-M3 regression: the LangGraph wrapper yields the same specialist result
as the direct deterministic pipeline (plan.md M3 완료 기준)."""

import io

import pytest
from docx import Document

from app.agents.graph import run_review_graph
from app.parsers.docx_parser import parse_docx
from app.review import review_with_verification


def _docx(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_graph_matches_direct_pipeline() -> None:
    data = _docx(
        [
            "본 연구는 (Kim, 2023)와 (Ghost, 2099)를 검토한다.",
            "References",
            "Kim, S. (2023). A study. Journal of X, 1(1), 1-10.",
        ]
    )
    document = parse_docx(data)

    direct = await review_with_verification(document)
    state = await run_review_graph(document)

    assert state["match_report"].stats == direct.match_report.stats
    assert [p.id for p in state["patch_proposals"]] == [p.id for p in direct.patches]
    # Critics are attached by the graph path.
    assert "consistency" in state
    assert state["consistency"].agent == "C4-ConsistencyAuditor"
