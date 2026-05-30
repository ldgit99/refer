from app.citation.extractor import InTextCitation
from app.citation.matcher import match
from app.citation.references import ReferenceItem


def _cit(raw: str, authors: list[str], year: int, **kw) -> InTextCitation:
    return InTextCitation(
        raw=raw,
        style=kw.get("style", "author_year"),
        authors=authors,
        year=year,
        numbers=kw.get("numbers", []),
        paragraph_index=0,
        char_start=0,
        char_end=len(raw),
    )


def _ref(idx: int, authors: list[str], year: int, number: int | None = None) -> ReferenceItem:
    return ReferenceItem(
        index=idx,
        raw=f"{', '.join(authors)} ({year}).",
        authors=authors,
        year=year,
        number=number,
    )


def test_clean_match_has_no_issues() -> None:
    cits = [_cit("(Kim, 2023)", ["Kim"], 2023)]
    refs = [_ref(0, ["Kim"], 2023)]
    report = match(cits, refs)
    assert report.stats["issues"] == 0


def test_orphan_citation() -> None:
    cits = [_cit("(Nobody, 2021)", ["Nobody"], 2021)]
    refs = [_ref(0, ["Kim"], 2023)]
    report = match(cits, refs)
    assert any(i.type == "orphan_citation" for i in report.issues)


def test_orphan_reference() -> None:
    cits = [_cit("(Kim, 2023)", ["Kim"], 2023)]
    refs = [_ref(0, ["Kim"], 2023), _ref(1, ["Park"], 2019)]
    report = match(cits, refs)
    assert any(i.type == "orphan_reference" for i in report.issues)


def test_year_mismatch() -> None:
    cits = [_cit("(Kim, 2023)", ["Kim"], 2023)]
    refs = [_ref(0, ["Kim"], 2024)]
    report = match(cits, refs)
    assert any(i.type == "year_mismatch" for i in report.issues)


def test_author_count_mismatch_et_al() -> None:
    cits = [_cit("(Kim, Lee & Park, 2023)", ["Kim", "Lee", "Park"], 2023)]
    refs = [_ref(0, ["Kim", "Lee", "Park"], 2023)]
    report = match(cits, refs)
    assert any(i.type == "author_count_mismatch" for i in report.issues)


def test_numeric_orphan() -> None:
    cits = [_cit("[5]", [], 0, style="numeric", numbers=[5])]
    refs = [_ref(0, ["Kim"], 2023, number=1)]
    report = match(cits, refs)
    assert any(i.type == "orphan_citation" for i in report.issues)
