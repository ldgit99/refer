"""F3 verification tests with a respx-mocked Crossref (no real network)."""

import httpx
import pytest
import respx

from app.citation.csl import CSLItem, CSLName
from app.verifier.crossref import CrossrefClient
from app.verifier.verify import verify_reference


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


@pytest.mark.asyncio
@respx.mock
async def test_valid_doi_verified() -> None:
    doi = "10.1000/xyz"
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            json=_doi_csl("A study of things", "Kim", 2024, doi),
            headers={"content-type": "application/vnd.citationstyles.csl+json"},
        )
    )
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
async def test_invalid_doi_flagged() -> None:
    doi = "10.0000/missing"
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(404)
    )
    ref = CSLItem(id="r1", title="Ghost paper", doi=doi)
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "invalid_doi"
    assert result.severity == "CRITICAL"
    assert result.doi_resolves is False


@pytest.mark.asyncio
@respx.mock
async def test_doi_mismatch_downgraded() -> None:
    """EvidenceCritic-style guard: DOI exists but metadata disagrees."""
    doi = "10.1000/realbutwrong"
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            json=_doi_csl("Completely different paper", "Yi", 2010, doi),
            headers={"content-type": "application/vnd.citationstyles.csl+json"},
        )
    )
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
async def test_doi_link_resolves_but_crossref_missing_is_invalid() -> None:
    doi = "10.1000/resolver-only"
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            json=_doi_csl("A study of things", "Kim", 2024, doi),
            headers={"content-type": "application/vnd.citationstyles.csl+json"},
        )
    )
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(404)
    )
    ref = CSLItem(
        id="r2b",
        title="A study of things",
        author=[CSLName(family="Kim")],
        issued_year=2024,
        doi=doi,
    )
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "invalid_doi"
    assert result.doi_resolves is True
    assert result.title_matches is True


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
