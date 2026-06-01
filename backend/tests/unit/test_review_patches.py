import pytest

from app.citation.csl import CSLItem
from app.citation.extractor import extract_from_text
from app.citation.matcher import MatchReport, match
from app.citation.references import ReferenceItem, parse_references
from app.parsers.base import build_document
from app.review import build_patches, review_with_verification
from app.verifier.verify import VerifiedItem


def test_every_f1_issue_becomes_a_suggestion() -> None:
    # orphan_citation (body) + orphan_reference + duplicate_reference (list-level)
    # must all yield a suggestion, not just the body-anchored one.
    document = build_document(
        [
            "본 연구는 (Ghost, 2099)를 인용한다.",
            "참고문헌",
            "Kim, S. (2023). Cited work. Journal, 1(1), 1-2.",
            "Kim, S. (2023). Cited work. Journal, 1(1), 1-2.",
            "Lee, J. (2008). Never cited. Journal, 2(2), 3-4.",
        ]
    )
    citations = []
    for para in document.body_paragraphs():
        citations.extend(extract_from_text(para.text, para.index))
    references = parse_references(document.references_section)
    report = match(citations, references)

    issue_types = {i.type for i in report.issues}
    assert {"orphan_citation", "orphan_reference", "duplicate_reference"} <= issue_types

    patches = build_patches(document, report, csl_items=[], verified={})
    f1_types = {p.comment.split("]")[0].replace("[F1 ", "") for p in patches if p.source == "F1"}
    # Every F1 issue type is represented in the suggestions.
    assert {"orphan_citation", "orphan_reference", "duplicate_reference"} <= f1_types
    assert len([p for p in patches if p.source == "F1"]) == len(report.issues)


class FailingCrossrefClient:
    async def doi_url_resolves(self, doi: str):  # noqa: ANN201, ARG002
        raise RuntimeError("doi.org unavailable")

    async def resolve_doi_csl(self, doi: str):  # noqa: ANN201, ARG002
        raise RuntimeError("doi.org unavailable")

    async def get_work(self, doi: str):  # noqa: ANN201, ARG002
        raise RuntimeError("Crossref unavailable")

    async def search_bibliographic(self, query: str, rows: int = 5):  # noqa: ANN201, ARG002
        raise RuntimeError("Crossref search unavailable")


def test_dead_doi_creates_warning_patch() -> None:
    document = build_document(
        [
            "Body (Kim, 2024).",
            "References",
            "Kim, S. (2024). A study. Journal, 1(1), 1-2. https://doi.org/10.1000/dead",
        ]
    )
    ref = ReferenceItem(
        index=0,
        raw="Kim, S. (2024). A study. Journal, 1(1), 1-2. https://doi.org/10.1000/dead",
        authors=["Kim"],
        year=2024,
    )
    patches = build_patches(
        document=document,
        report=MatchReport(references=[ref]),
        csl_items=[CSLItem(id="ref-0", title="A study", doi="10.1000/dead")],
        verified={
            "ref-0": VerifiedItem(
                ref_id="ref-0",
                status="invalid_doi",
                doi="10.1000/dead",
                doi_url="https://doi.org/10.1000/dead",
                doi_resolves=False,
                severity="CRITICAL",
                note="DOI link did not open.",
            )
        },
    )
    assert len(patches) == 1
    assert patches[0].kind == "citation_comment"
    assert patches[0].source == "F3"
    assert "invalid_doi" in patches[0].comment


def test_verified_doi_creates_no_patch() -> None:
    document = build_document(["Body.", "References", "Kim, S. (2024). x."])
    ref = ReferenceItem(index=0, raw="Kim, S. (2024). x.", authors=["Kim"], year=2024)
    patches = build_patches(
        document=document,
        report=MatchReport(references=[ref]),
        csl_items=[CSLItem(id="ref-0", title="x", doi="10.1/ok")],
        verified={"ref-0": VerifiedItem(ref_id="ref-0", status="verified", doi_resolves=True)},
    )
    assert patches == []


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
    assert "inconclusive" in verified.note
    assert any(p.source == "F3" and "skipped" in p.comment for p in result.patches)
