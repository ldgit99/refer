from app.citation.extractor import extract_from_text


def test_author_year_basic() -> None:
    cits = extract_from_text("연구에 따르면 (Kim, 2023) 효과가 있다.", 0)
    assert len(cits) == 1
    c = cits[0]
    assert c.style == "author_year"
    assert c.authors == ["Kim"]
    assert c.year == 2023


def test_author_year_two_authors_and_suffix() -> None:
    cits = extract_from_text("(Lee & Park, 2024a)", 0)
    assert len(cits) == 1
    c = cits[0]
    assert c.year == 2024
    assert c.suffix == "a"
    assert "Lee" in c.authors and "Park" in c.authors


def test_korean_author_year() -> None:
    cits = extract_from_text("선행연구(이동국, 2024)에서는", 0)
    assert len(cits) == 1
    assert cits[0].style == "korean_author_year"
    assert cits[0].authors == ["이동국"]
    assert cits[0].year == 2024


def test_numeric_range() -> None:
    cits = extract_from_text("기존 연구[3, 5-7]에서", 0)
    assert len(cits) == 1
    assert cits[0].style == "numeric"
    assert cits[0].numbers == [3, 5, 6, 7]


def test_narrative() -> None:
    cits = extract_from_text("Smith (2020) reported a strong effect.", 0)
    assert any(c.style == "narrative" and c.year == 2020 for c in cits)


def test_paragraph_index_and_offsets() -> None:
    text = "앞부분 (Kim, 2023) 뒷부분"
    cits = extract_from_text(text, 7)
    c = cits[0]
    assert c.paragraph_index == 7
    assert text[c.char_start : c.char_end] == "(Kim, 2023)"
