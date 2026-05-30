import pytest

from app.citation.references import ReferenceItem
from app.llm.reference_parser import refine_references_with_llm


@pytest.mark.asyncio
async def test_llm_reference_parser_refines_mixed_reference(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    from app.config import get_settings

    get_settings.cache_clear()

    async def fake_chat(messages):  # noqa: ANN001, ANN202
        assert "김철수" in messages[-1]["content"]
        return {
            "references": [
                {
                    "index": 0,
                    "authors": ["Kim", "Lee"],
                    "year": 2024,
                    "suffix": None,
                    "title": "A mixed Korean English study",
                    "container_title": "Journal of Tests",
                    "type": "article-journal",
                    "volume": "12",
                    "issue": "1",
                    "page": "1-10",
                    "publisher": "",
                    "doi": "10.1000/test",
                    "url": "",
                    "confidence": 0.92,
                }
            ]
        }

    refs = [
        ReferenceItem(
            index=0,
            raw="김철수, Lee, J. (2024). A mixed Korean English study. Journal of Tests.",
        )
    ]

    refined_refs, csl_items, used = await refine_references_with_llm(refs, chat=fake_chat)

    assert used is True
    assert refined_refs[0].authors == ["Kim", "Lee"]
    assert refined_refs[0].year == 2024
    assert csl_items[0].title == "A mixed Korean English study"
    assert csl_items[0].doi == "10.1000/test"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_llm_reference_parser_falls_back_on_bad_payload(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    from app.config import get_settings

    get_settings.cache_clear()

    async def fake_chat(messages):  # noqa: ANN001, ANN202, ARG001
        return {"unexpected": []}

    refs = [ReferenceItem(index=0, raw="Kim, S. (2024). A study.")]

    refined_refs, csl_items, used = await refine_references_with_llm(refs, chat=fake_chat)

    assert used is False
    assert refined_refs == refs
    assert csl_items[0].id == "ref-0"

    get_settings.cache_clear()
