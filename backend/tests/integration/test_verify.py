"""F3 verification tests with a respx-mocked Crossref (no real network)."""

import httpx
import pytest
import respx

from app.citation.csl import CSLItem, CSLName
from app.verifier.crossref import CrossrefClient
from app.verifier.verify import extract_doi, normalize_doi, verify_reference


def _crossref_work(title: str, family: str, year: int, doi: str) -> dict:
    return {
        "message": {
            "DOI": doi,
            "title": [title],
            "author": [{"family": family, "given": "A"}],
            "issued": {"date-parts": [[year]]},
            "container-title": ["Journal of Things"],
            "type": "journal-article",
        }
    }


def _doi_csl(title: str, family: str, year: int, doi: str) -> dict:
    return {
        "DOI": doi,
        "title": title,
        "author": [{"family": family, "given": "A"}],
        "issued": {"date-parts": [[year]]},
        "container-title": "Journal of Things",
        "type": "article-journal",
    }


def _mock_doi_link(doi: str, status_code: int = 200) -> None:
    respx.get(
        f"https://doi.org/{doi}",
        headers__contains={"Accept": "text/html,application/xhtml+xml"},
    ).mock(return_value=httpx.Response(status_code, text="<html></html>"))


def _mock_doi_csl(doi: str, title: str, family: str, year: int) -> None:
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            json=_doi_csl(title, family, year, doi),
            headers={"content-type": "application/vnd.citationstyles.csl+json"},
        )
    )


def test_normalize_doi_accepts_urls_labels_and_wrappers() -> None:
    assert normalize_doi("https://doi.org/10.3102/003465430298487") == "10.3102/003465430298487"
    assert normalize_doi("doi:10.1000/ABC.") == "10.1000/abc"
    assert extract_doi("(https://doi.org/10.1000/foo)") == "10.1000/foo"
    assert extract_doi("https://doi.org/10.1000/foo(bar)") == "10.1000/foo(bar)"


@pytest.mark.asyncio
@respx.mock
async def test_valid_doi_verified() -> None:
    doi = "10.1000/xyz"
    _mock_doi_link(doi)
    _mock_doi_csl(doi, "A study of things", "Kim", 2024)
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(
            200, json=_crossref_work("A study of things", "Kim", 2024, doi)
        )
    )
    ref = CSLItem(
        id="r0",
        title="A study of things",
        author=[CSLName(family="Kim")],
        issued_year=2024,
        doi=doi,
    )
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "verified"
    assert result.confidence >= 0.9
    assert result.doi_url == f"https://doi.org/{doi}"
    assert result.doi_resolves is True
    assert result.title_matches is True


@pytest.mark.asyncio
@respx.mock
async def test_full_doi_url_in_csl_item_is_normalized_before_verification() -> None:
    doi = "10.3102/003465430298487"
    _mock_doi_link(doi)
    _mock_doi_csl(doi, "The Power of Feedback", "Hattie", 2007)
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(
            200, json=_crossref_work("The Power of Feedback", "Hattie", 2007, doi)
        )
    )
    ref = CSLItem(
        id="r0-url",
        title="The power of feedback",
        author=[CSLName(family="Hattie")],
        issued_year=2007,
        doi=f"https://doi.org/{doi}",
    )

    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)

    assert result.status == "verified"
    assert result.doi_url == f"https://doi.org/{doi}"
    assert result.doi_resolves is True


@pytest.mark.asyncio
@respx.mock
async def test_invalid_doi_flagged() -> None:
    doi = "10.0000/missing"
    _mock_doi_link(doi, 404)
    ref = CSLItem(id="r1", title="Ghost paper", doi=doi)
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "invalid_doi"
    assert result.severity == "CRITICAL"
    assert result.doi_resolves is False


@pytest.mark.asyncio
@respx.mock
async def test_doi_mismatch_downgraded() -> None:
    doi = "10.1000/realbutwrong"
    _mock_doi_link(doi)
    _mock_doi_csl(doi, "Completely different paper", "Yi", 2010)
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(
            200, json=_crossref_work("Completely different paper", "Yi", 2010, doi)
        )
    )
    ref = CSLItem(
        id="r2",
        title="A study of citation tools in Korean education",
        author=[CSLName(family="Lee")],
        issued_year=2024,
        doi=doi,
    )
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "doi_mismatch"
    assert result.severity == "WARNING"
    assert result.doi_resolves is True
    assert result.title_matches is False


@pytest.mark.asyncio
@respx.mock
async def test_doi_link_resolves_but_crossref_missing_is_not_found() -> None:
    doi = "10.1000/resolver-only"
    _mock_doi_link(doi)
    _mock_doi_csl(doi, "A study of things", "Kim", 2024)
    respx.get(f"https://api.crossref.org/works/{doi}").mock(return_value=httpx.Response(404))
    ref = CSLItem(
        id="r2b",
        title="A study of things",
        author=[CSLName(family="Kim")],
        issued_year=2024,
        doi=doi,
    )
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "not_found"
    assert result.doi_resolves is True
    assert result.title_matches is True


@pytest.mark.asyncio
@respx.mock
async def test_doi_browser_link_resolves_without_csl_json_is_not_invalid() -> None:
    doi = "10.1000/html-only"
    _mock_doi_link(doi)
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200, text="<html></html>", headers={"content-type": "text/html"}
        )
    )
    respx.get(f"https://api.crossref.org/works/{doi}").mock(return_value=httpx.Response(404))
    ref = CSLItem(id="r2c", title="A study of things", doi=doi)

    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)

    assert result.status == "not_found"
    assert result.severity == "WARNING"
    assert result.doi_resolves is True
    assert result.title_matches is None


@pytest.mark.asyncio
@respx.mock
async def test_doi_csl_missing_but_crossref_title_matches_is_verified() -> None:
    doi = "10.1000/crossref-only"
    _mock_doi_link(doi)
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200, text="<html></html>", headers={"content-type": "text/html"}
        )
    )
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(
            200, json=_crossref_work("A study of things", "Kim", 2024, doi)
        )
    )
    ref = CSLItem(
        id="r2d",
        title="A study of things",
        author=[CSLName(family="Kim")],
        issued_year=2024,
        doi=doi,
    )

    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)

    assert result.status == "verified"
    assert result.doi_resolves is True
    assert result.title_matches is True


@pytest.mark.asyncio
@respx.mock
async def test_doi_redirect_counts_as_resolved_even_if_publisher_blocks_bot() -> None:
    doi = "10.1000/redirect"
    respx.get(
        f"https://doi.org/{doi}",
        headers__contains={"Accept": "text/html,application/xhtml+xml"},
    ).mock(
        return_value=httpx.Response(
            302,
            headers={"location": "https://publisher.example/blocked"},
        )
    )
    _mock_doi_csl(doi, "A study of things", "Kim", 2024)
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(
            200, json=_crossref_work("A study of things", "Kim", 2024, doi)
        )
    )
    ref = CSLItem(
        id="r2e",
        title="A study of things",
        author=[CSLName(family="Kim")],
        issued_year=2024,
        doi=doi,
    )

    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)

    assert result.status == "verified"
    assert result.doi_resolves is True


@pytest.mark.asyncio
@respx.mock
async def test_missing_doi_suggested() -> None:
    title = "A unique and findable title about citations"
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        _crossref_work(title, "Kim", 2024, "10.1/found")["message"]
                    ]
                }
            },
        )
    )
    ref = CSLItem(
        id="r3", title=title, author=[CSLName(family="Kim")], issued_year=2024
    )
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "doi_suggested"
    assert result.suggested_doi == "10.1/found"
