import pytest

from app.citation.csl import CSLItem
from app.citation.matcher import MatchReport
from app.citation.references import ReferenceItem
from app.parsers.base import build_document
from app.review import build_patches, review_with_verification
from app.verifier.verify import VerifiedItem


class FailingCrossrefClient:
    async def doi_url_resolves(self, doi: str):  # noqa: ANN201, ARG002
        raise RuntimeError("doi.org unavailable")

    async def resolve_doi_csl(self, doi: str):  # noqa: ANN201, ARG002
        raise RuntimeError("doi.org unavailable")

    async def get_work(self, doi: str):  # noqa: ANN201, ARG002
        raise RuntimeError("Crossref unavailable")

    async def search_bibliographic(self, query: str, rows: int = 5):  # noqa: ANN201, ARG002
        raise RuntimeError("Crossref search unavailable")


def test_doi_suggestion_creates_patch() -> None:
    document = build_document(
        [
            "Body (Kim, 2024).",
            "References",
            "Kim, S. (2024). A study. Journal, 1(1), 1-2.",
        ]
    )
    ref = ReferenceItem(
        index=0,
        raw="Kim, S. (2024). A study. Journal, 1(1), 1-2.",
        authors=["Kim"],
        year=2024,
    )
    patches = build_patches(
        document=document,
        report=MatchReport(references=[ref]),
        formatted={},
        csl_items=[CSLItem(id="ref-0", title="A study")],
        verified={
            "ref-0": VerifiedItem(
                ref_id="ref-0",
                status="doi_suggested",
                confidence=0.96,
                suggested_doi="10.1000/found",
                severity="INFO",
            )
        },
    )
    assert len(patches) == 1
    assert patches[0].kind == "doi_insert"
    assert "https://doi.org/10.1000/found" in patches[0].after


@pytest.mark.asyncio
async def test_doi_verification_failure_is_reported() -> None:
    document = build_document(
        [
            "Body (Kim, 2024).",
            "References",
            "Kim, S. (2024). A study. Journal, 1(1), 1-2. https://doi.org/10.1000/found",
        ]
    )

    result = await review_with_verification(document, client=FailingCrossrefClient())

    verified = result.verified["ref-0"]
    assert verified.status == "skipped"
    assert verified.doi_url == "https://doi.org/10.1000/found"
    assert "doi.org unavailable" in verified.note
    assert any(p.source == "F3" and "skipped" in p.comment for p in result.patches)
