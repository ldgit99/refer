"""Tests for the F1 matcher accuracy improvements."""

from app.citation.extractor import InTextCitation
from app.citation.matcher import match
from app.citation.references import ReferenceItem


def _cit(raw: str, authors: list[str], year: int, **kw) -> InTextCitation:
    return InTextCitation(
        raw=raw,
        style=kw.get("style", "author_year"),
        authors=authors,
        year=year,
        suffix=kw.get("suffix"),
        numbers=kw.get("numbers", []),
        paragraph_index=0,
        char_start=0,
        char_end=len(raw),
    )


def _ref(idx: int, authors: list[str], year: int, number: int | None = None) -> ReferenceItem:
    return ReferenceItem(
        index=idx,
        raw=f"{', '.join(authors)} ({year}). Title.",
        authors=authors,
        year=year,
        number=number,
    )


def test_same_author_two_years_picks_matching_year() -> None:
    # Two Kim references; the 2024 citation must match the 2024 ref, not 2020.
    cits = [_cit("(Kim, 2024)", ["Kim"], 2024)]
    refs = [_ref(0, ["Kim"], 2020), _ref(1, ["Kim"], 2024)]
    report = match(cits, refs)
    # No year_mismatch because the correct candidate was chosen.
    assert report.stats["year_mismatch"] == 0
    # The 2020 ref is the orphan, not 2024.
    orphans = [i for i in report.issues if i.type == "orphan_reference"]
    assert len(orphans) == 1
    assert orphans[0].reference_index == 0


def test_reverse_et_al_violation() -> None:
    # Two-author work but cited with "et al." -> violation.
    cits = [_cit("(Kim et al., 2023)", ["Kim"], 2023)]
    refs = [_ref(0, ["Kim", "Lee"], 2023)]
    report = match(cits, refs)
    assert report.stats["author_count_mismatch"] == 1


def test_duplicate_reference_detected() -> None:
    cits = [_cit("(Kim, 2023)", ["Kim"], 2023)]
    refs = [_ref(0, ["Kim"], 2023), _ref(1, ["Kim"], 2023)]
    report = match(cits, refs)
    assert report.stats["duplicate_reference"] == 1


def test_explicit_numbers_not_clobbered_by_position() -> None:
    cits = [_cit("[2]", [], 0, style="numeric", numbers=[2])]
    refs = [
        ReferenceItem(index=0, raw="[5] A. (2020).", authors=["A"], year=2020, number=5),
        ReferenceItem(index=1, raw="[2] B. (2021).", authors=["B"], year=2021, number=2),
    ]
    report = match(cits, refs)
    # [2] resolves to the ref with explicit number 2 (index 1), so no orphan citation.
    assert report.stats["orphan_citation"] == 0
