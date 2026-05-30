from app.citation.ref_to_csl import reference_to_csl
from app.citation.references import parse_references


def test_latin_journal_reference() -> None:
    section = (
        "Kim, S., & Lee, J. (2024). A study of things. "
        "Journal of X, 12(3), 45-67. https://doi.org/10.1000/xyz"
    )
    refs = parse_references(section)
    csl = reference_to_csl(refs[0])
    assert csl.issued_year == 2024
    assert any(a.family == "Kim" for a in csl.author)
    assert csl.title.startswith("A study of things")
    assert csl.doi == "10.1000/xyz"


def test_reference_without_doi() -> None:
    section = "Park, H. (2019). Some title here. Some Journal, 1(1), 1-10."
    refs = parse_references(section)
    csl = reference_to_csl(refs[0])
    assert csl.doi == ""
    assert csl.issued_year == 2019
