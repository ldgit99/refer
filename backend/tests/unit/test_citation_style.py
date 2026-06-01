from app.citation.extractor import InTextCitation
from app.citation.references import ReferenceItem
from app.citation.style import detect_citation_style


def test_detects_apa_from_author_year_citations_and_references() -> None:
    profile = detect_citation_style(
        citations=[
            InTextCitation(
                raw="(Kim, 2024)",
                style="author_year",
                authors=["Kim"],
                year=2024,
                paragraph_index=0,
                char_start=0,
                char_end=11,
            )
        ],
        references=[
            ReferenceItem(
                index=0,
                raw="Kim, S. (2024). A study. Journal, 1(1), 1-2.",
                authors=["Kim"],
                year=2024,
            )
        ],
    )

    assert profile.system == "apa"
    assert profile.confidence == 1


def test_detects_ieee_from_numeric_citations_and_numbered_references() -> None:
    profile = detect_citation_style(
        citations=[
            InTextCitation(
                raw="[1]",
                style="numeric",
                numbers=[1],
                paragraph_index=0,
                char_start=0,
                char_end=3,
            )
        ],
        references=[
            ReferenceItem(
                index=0,
                raw="[1] A. Author, Title, 2024.",
                year=2024,
                number=1,
            )
        ],
    )

    assert profile.system == "ieee"
    assert profile.confidence == 1


def test_detects_mixed_style_when_signals_conflict() -> None:
    profile = detect_citation_style(
        citations=[
            InTextCitation(
                raw="[1]",
                style="numeric",
                numbers=[1],
                paragraph_index=0,
                char_start=0,
                char_end=3,
            ),
            InTextCitation(
                raw="(Kim, 2024)",
                style="author_year",
                authors=["Kim"],
                year=2024,
                paragraph_index=1,
                char_start=0,
                char_end=11,
            ),
        ],
        references=[
            ReferenceItem(index=0, raw="[1] A. Author, Title, 2024.", year=2024, number=1),
            ReferenceItem(
                index=1,
                raw="Kim, S. (2024). A study. Journal, 1(1), 1-2.",
                authors=["Kim"],
                year=2024,
            ),
        ],
    )

    assert profile.system == "mixed"
