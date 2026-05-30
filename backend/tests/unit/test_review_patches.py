from app.citation.csl import CSLItem
from app.citation.matcher import MatchReport
from app.citation.references import ReferenceItem
from app.parsers.base import build_document
from app.review import build_patches
from app.verifier.verify import VerifiedItem


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
