from app.citation.csl import CSLItem, CSLName
from app.citation.formatter import format_apa


def test_format_journal_article() -> None:
    item = CSLItem(
        id="r1",
        type="article-journal",
        author=[CSLName(family="Kim", given="Soo Jin"), CSLName(family="Lee", given="Ho")],
        issued_year=2024,
        title="A study of citation tools",
        container_title="Journal of Educational Technology",
        volume="40",
        issue="1",
        page="1-20",
        doi="10.1234/abcd",
    )
    out = format_apa(item)
    assert "Kim, S. J." in out
    assert "& Lee, H." in out
    assert "(2024)." in out
    assert "Journal of Educational Technology, 40(1), 1-20." in out
    assert "https://doi.org/10.1234/abcd" in out


def test_format_book_uses_publisher() -> None:
    item = CSLItem(
        id="r2",
        type="book",
        author=[CSLName(family="Park", given="Jae")],
        issued_year=2020,
        title="Academic writing",
        publisher="Hanbit",
    )
    out = format_apa(item)
    assert "Hanbit." in out
    assert "Academic writing." in out


def test_format_no_year_is_nd() -> None:
    item = CSLItem(id="r3", title="Untitled", author=[CSLName(family="Anon")])
    assert "(n.d.)." in format_apa(item)
