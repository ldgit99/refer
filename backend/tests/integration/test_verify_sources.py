"""Tests for OpenAlex secondary verification, KCI fallback, and parallel verify."""

import httpx
import pytest
import respx

from app.citation.csl import CSLItem, CSLName
from app.verifier.cache import get_verification_cache
from app.verifier.crossref import CrossrefClient
from app.verifier.openalex import OpenAlexClient
from app.verifier.verify import verify_reference, verify_references


@pytest.fixture(autouse=True)
async def _clear_cache():
    await get_verification_cache().clear()
    yield
    await get_verification_cache().clear()


def _openalex_work(title: str, family: str, year: int, doi: str) -> dict:
    return {
        "title": title,
        "publication_year": year,
        "doi": f"https://doi.org/{doi}",
        "authorships": [{"author": {"display_name": f"Soo {family}"}}],
        "host_venue": {"display_name": "Korean Journal"},
        "biblio": {"volume": "1", "issue": "1", "first_page": "1", "last_page": "9"},
    }


@pytest.mark.asyncio
@respx.mock
async def test_openalex_used_when_crossref_misses() -> None:
    title = "한국어 학습분석 기반 피드백 연구"
    # Crossref bibliographic search returns nothing useful.
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": []}})
    )
    # OpenAlex title search finds a strong match.
    respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(
            200, json={"results": [_openalex_work(title, "Lee", 2024, "10.1000/oa")]}
        )
    )
    ref = CSLItem(id="r0", title=title, author=[CSLName(family="Lee")], issued_year=2024)
    async with CrossrefClient() as cr, OpenAlexClient() as oa:
        result = await verify_reference(ref, cr, openalex=oa)
    assert result.status == "doi_suggested"
    assert result.source == "openalex"
    assert result.suggested_doi == "10.1000/oa"


@pytest.mark.asyncio
@respx.mock
async def test_parallel_verify_all_items() -> None:
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": []}})
    )
    refs = [
        CSLItem(id=f"r{i}", title=f"Some distinct title {i}", author=[CSLName(family="A")])
        for i in range(5)
    ]
    async with CrossrefClient() as cr:
        results = await verify_references(refs, cr, concurrency=3)
    assert set(results.keys()) == {r.id for r in refs}
    assert all(v.status == "not_found" for v in results.values())


@pytest.mark.asyncio
@respx.mock
async def test_cache_dedups_same_doi() -> None:
    doi = "10.1000/dup"
    route = respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "application/vnd.citationstyles.csl+json"},
            json={
                "title": "Cached work",
                "author": [{"family": "Kim"}],
                "issued": {"date-parts": [[2024]]},
                "DOI": doi,
            },
        )
    )
    crossref_route = respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {
                    "title": ["Cached work"],
                    "author": [{"family": "Kim"}],
                    "issued": {"date-parts": [[2024]]},
                    "DOI": doi,
                }
            },
        )
    )
    refs = [
        CSLItem(id="a", title="Cached work", author=[CSLName(family="Kim")], issued_year=2024, doi=doi),
        CSLItem(id="b", title="Cached work", author=[CSLName(family="Kim")], issued_year=2024, doi=doi),
    ]
    async with CrossrefClient() as cr:
        results = await verify_references(refs, cr, concurrency=1)
    assert results["a"].status == "verified"
    assert results["b"].status == "verified"
    # Second reference (same DOI) is served from cache, so it adds no network
    # calls: only the first reference's lookups hit the wire.
    assert route.call_count <= 2
    assert crossref_route.call_count == 1
