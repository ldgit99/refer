from app.citation.references import parse_references


def test_latin_apa_entry() -> None:
    section = "Kim, S., & Lee, J. (2024). A study of things. Journal of X, 1(2), 3-4."
    refs = parse_references(section)
    assert len(refs) == 1
    r = refs[0]
    assert r.year == 2024
    assert "Kim" in r.authors and "Lee" in r.authors


def test_numbered_entries() -> None:
    section = (
        "[1] A. Author, Title one, 2019.\n"
        "[2] B. Writer, Title two, 2020.\n"
    )
    refs = parse_references(section)
    assert len(refs) == 2
    assert refs[0].number == 1
    assert refs[1].number == 2
    assert refs[1].year == 2020


def test_korean_entry() -> None:
    section = "이동국 (2024). 한국어 논문 제목. 한국교육공학연구, 40(1), 1-20."
    refs = parse_references(section)
    assert len(refs) == 1
    assert refs[0].year == 2024
    assert "이동국" in refs[0].authors


def test_empty_section() -> None:
    assert parse_references(None) == []
    assert parse_references("") == []
