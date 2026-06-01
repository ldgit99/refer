"""F3 tests — DOI link verification ("does the DOI link open?").

No title/metadata comparison. A Crossref record or doi.org content negotiation
proves the link is live (so serverless bot-blocks on the publisher page do not
cause false failures); the browser-style resolve is a corroborating signal.
"""

import httpx
import pytest
import respx

from app.citation.csl import CSLItem, CSLName
from app.verifier.crossref import CrossrefClient
from app.verifier.verify import extract_doi, normalize_doi, verify_reference


def _crossref_message(doi: str) -> dict:
    return {
        "message": {
            "DOI": doi,
            "title": ["Some work"],
            "author": [{"family": "Kim", "given": "A"}],
            "issued": {"date-parts": [[2024]]},
            "type": "journal-article",
        }
    }


def _mock_doi_link(doi: str, status_code: int = 302) -> None:
    respx.get(
        f"https://doi.org/{doi}",
        headers__contains={"Accept": "text/html,application/xhtml+xml"},
    ).mock(return_value=httpx.Response(status_code, text=""))


def _mock_doi_csl(doi: str) -> None:
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            json={"DOI": doi, "title": "Some work"},
            headers={"content-type": "application/vnd.citationstyles.csl+json"},
        )
    )


def test_normalize_doi_accepts_urls_labels_and_wrappers() -> None:
    assert normalize_doi("https://doi.org/10.3102/003465430298487") == "10.3102/003465430298487"
    assert normalize_doi("doi:10.1000/ABC.") == "10.1000/abc"
    assert extract_doi("(https://doi.org/10.1000/foo)") == "10.1000/foo"


@pytest.mark.asyncio
@respx.mock
async def test_crossref_record_means_link_opens() -> None:
    doi = "10.3390/su151712921"
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(200, json=_crossref_message(doi))
    )
    ref = CSLItem(id="r0", title="x", author=[CSLName(family="Kim")], doi=doi)
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "verified"
    assert result.doi_resolves is True
    assert result.source == "crossref"


@pytest.mark.asyncio
@respx.mock
async def test_botblocked_resolve_but_crossref_record_is_verified() -> None:
    # Publisher landing page bot-blocks the browser resolve, but Crossref has the
    # record -> the DOI link is considered to open (no false "link failed").
    doi = "10.1163/23641177-bja10001"
    respx.get(
        f"https://doi.org/{doi}",
        headers__contains={"Accept": "text/html,application/xhtml+xml"},
    ).mock(side_effect=httpx.ConnectError("blocked"))
    respx.get(f"https://api.crossref.org/works/{doi}").mock(
        return_value=httpx.Response(200, json=_crossref_message(doi))
    )
    ref = CSLItem(id="r1", title="x", doi=doi)
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "verified"
    assert result.severity == "INFO"


@pytest.mark.asyncio
@respx.mock
async def test_doi_content_negotiation_means_link_opens() -> None:
    doi = "10.1000/resolver-only"
    respx.get(f"https://api.crossref.org/works/{doi}").mock(return_value=httpx.Response(404))
    _mock_doi_csl(doi)
    ref = CSLItem(id="r2", title="x", doi=doi)
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "verified"
    assert result.source == "doi.org"


@pytest.mark.asyncio
@respx.mock
async def test_browser_resolve_redirect_means_link_opens() -> None:
    doi = "10.1000/html-only"
    respx.get(f"https://api.crossref.org/works/{doi}").mock(return_value=httpx.Response(404))
    # content negotiation returns non-JSON -> treated as no metadata
    respx.get(f"https://doi.org/{doi}").mock(
        return_value=httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})
    )
    _mock_doi_link(doi, 302)
    ref = CSLItem(id="r3", title="x", doi=doi)
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "verified"
    assert result.doi_resolves is True


@pytest.mark.asyncio
@respx.mock
async def test_dead_doi_is_invalid() -> None:
    doi = "10.0000/missing"
    respx.get(f"https://api.crossref.org/works/{doi}").mock(return_value=httpx.Response(404))
    respx.get(f"https://doi.org/{doi}").mock(return_value=httpx.Response(404))
    _mock_doi_link(doi, 404)
    ref = CSLItem(id="r4", title="x", doi=doi)
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "invalid_doi"
    assert result.severity == "CRITICAL"


@pytest.mark.asyncio
async def test_reference_without_doi_is_no_doi() -> None:
    ref = CSLItem(id="r5", title="A title with no DOI", author=[CSLName(family="Kim")])
    async with CrossrefClient() as client:
        result = await verify_reference(ref, client)
    assert result.status == "no_doi"
    assert result.severity == "INFO"
    assert result.doi is None
