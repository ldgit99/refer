"""LLM-assisted reference parsing for mixed Korean/English bibliographies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError

from app.citation.csl import CSLItem, CSLName
from app.citation.ref_to_csl import reference_to_csl
from app.citation.references import ReferenceItem
from app.config import get_settings
from app.llm.openai_client import ChatMessage, chat_json
from app.verifier.verify import extract_doi

ChatJSONFunc = Callable[[list[ChatMessage]], Awaitable[dict]]

MAX_LLM_REFERENCES = 40
MIN_PARSE_CONFIDENCE = 0.55


class ParsedReference(BaseModel):
    index: int
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    suffix: str | None = None
    title: str = ""
    container_title: str = ""
    type: str = "article-journal"
    volume: str = ""
    issue: str = ""
    page: str = ""
    publisher: str = ""
    doi: str = ""
    url: str = ""
    confidence: float = 0.0


class ParsedReferenceBatch(BaseModel):
    references: list[ParsedReference] = Field(default_factory=list)


def _prompt(references: list[ReferenceItem]) -> list[ChatMessage]:
    lines = "\n".join(f"{r.index}. {r.raw}" for r in references)
    return [
        {
            "role": "developer",
            "content": (
                "You parse academic reference-list entries into conservative JSON. "
                "Return JSON only. Preserve the given index. Use family names only in authors. "
                "Do not invent missing bibliographic facts. Set confidence from 0 to 1."
            ),
        },
        {
            "role": "user",
            "content": (
                "Parse these references. Return this exact shape: "
                '{"references":[{"index":0,"authors":["Family"],"year":2024,'
                '"suffix":null,"title":"","container_title":"","type":"article-journal",'
                '"volume":"","issue":"","page":"","publisher":"","doi":"","url":"",'
                '"confidence":0.0}]}.\n\n'
                f"{lines}"
            ),
        },
    ]


def _merge_reference_item(item: ReferenceItem, parsed: ParsedReference) -> ReferenceItem:
    if parsed.confidence < MIN_PARSE_CONFIDENCE:
        return item
    return item.model_copy(
        update={
            "authors": parsed.authors or item.authors,
            "year": parsed.year or item.year,
            "suffix": parsed.suffix or item.suffix,
        }
    )


def _merge_csl_item(item: CSLItem, parsed: ParsedReference) -> CSLItem:
    if parsed.confidence < MIN_PARSE_CONFIDENCE:
        return item
    authors = [CSLName(family=a) for a in parsed.authors if a.strip()] or item.author
    doi = (parsed.doi or item.doi or "").strip().lower()
    url = parsed.url or item.url
    if not doi and url:
        doi = extract_doi(url) or ""
    return item.model_copy(
        update={
            "type": parsed.type or item.type,
            "author": authors,
            "issued_year": parsed.year or item.issued_year,
            "title": parsed.title or item.title,
            "container_title": parsed.container_title or item.container_title,
            "volume": parsed.volume or item.volume,
            "issue": parsed.issue or item.issue,
            "page": parsed.page or item.page,
            "publisher": parsed.publisher or item.publisher,
            "doi": doi,
            "url": url,
        }
    )


async def refine_references_with_llm(
    references: list[ReferenceItem],
    *,
    chat: ChatJSONFunc = chat_json,
) -> tuple[list[ReferenceItem], list[CSLItem], bool]:
    settings = get_settings()
    deterministic_csl = [reference_to_csl(r) for r in references]
    if (
        settings.active_llm_provider != "openai"
        or not settings.openai_api_key
        or not references
    ):
        return references, deterministic_csl, False

    batch = references[:MAX_LLM_REFERENCES]
    try:
        payload = await chat(_prompt(batch))
        parsed_batch = ParsedReferenceBatch.model_validate(payload)
    except (ValidationError, RuntimeError, ValueError):
        return references, deterministic_csl, False

    parsed_by_index = {p.index: p for p in parsed_batch.references}
    refined_refs: list[ReferenceItem] = []
    refined_csl: list[CSLItem] = []

    for ref, csl in zip(references, deterministic_csl, strict=True):
        parsed = parsed_by_index.get(ref.index)
        if parsed is None:
            refined_refs.append(ref)
            refined_csl.append(csl)
            continue
        refined_refs.append(_merge_reference_item(ref, parsed))
        refined_csl.append(_merge_csl_item(csl, parsed))

    return refined_refs, refined_csl, bool(parsed_by_index)
