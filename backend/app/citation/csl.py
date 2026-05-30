"""CSL-JSON item model shared by F2 (formatter) and F3 (verifier).

A minimal subset of the CSL-JSON schema (research.md §4.3) sufficient for APA 7
journal/article/book formatting and Crossref/OpenAlex round-tripping.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CSLName(BaseModel):
    family: str = ""
    given: str = ""

    def as_dict(self) -> dict[str, str]:
        d: dict[str, str] = {}
        if self.family:
            d["family"] = self.family
        if self.given:
            d["given"] = self.given
        return d


class CSLItem(BaseModel):
    id: str
    type: str = "article-journal"
    author: list[CSLName] = Field(default_factory=list)
    issued_year: int | None = None
    title: str = ""
    container_title: str = ""  # journal / book title
    volume: str = ""
    issue: str = ""
    page: str = ""
    publisher: str = ""
    doi: str = ""
    url: str = ""

    def to_csl_json(self) -> dict:
        """Render to the dict shape citeproc-py expects."""
        data: dict = {"id": self.id, "type": self.type}
        if self.author:
            data["author"] = [a.as_dict() for a in self.author]
        if self.issued_year:
            data["issued"] = {"date-parts": [[self.issued_year]]}
        if self.title:
            data["title"] = self.title
        if self.container_title:
            data["container-title"] = self.container_title
        if self.volume:
            data["volume"] = self.volume
        if self.issue:
            data["issue"] = self.issue
        if self.page:
            data["page"] = self.page
        if self.publisher:
            data["publisher"] = self.publisher
        if self.doi:
            data["DOI"] = self.doi
        if self.url:
            data["URL"] = self.url
        return data

    @classmethod
    def from_crossref(cls, item_id: str, msg: dict) -> CSLItem:
        """Build a CSLItem from a Crossref ``/works`` message object."""
        authors = [
            CSLName(family=a.get("family", ""), given=a.get("given", ""))
            for a in msg.get("author", [])
        ]
        year: int | None = None
        for key in ("published-print", "published-online", "issued", "created"):
            val = msg.get(key)
            parts = val.get("date-parts") if isinstance(val, dict) else None
            if parts and parts[0] and parts[0][0]:
                year = int(parts[0][0])
                break
        title_list = msg.get("title") or [""]
        container_list = msg.get("container-title") or [""]
        return cls(
            id=item_id,
            type=msg.get("type", "article-journal"),
            author=authors,
            issued_year=year,
            title=title_list[0] if title_list else "",
            container_title=container_list[0] if container_list else "",
            volume=str(msg.get("volume", "")),
            issue=str(msg.get("issue", "")),
            page=str(msg.get("page", "")),
            publisher=str(msg.get("publisher", "")),
            doi=str(msg.get("DOI", "")),
            url=str(msg.get("URL", "")),
        )

    @classmethod
    def from_csl_json(cls, item_id: str, msg: dict) -> CSLItem:
        """Build a CSLItem from DOI content-negotiation CSL JSON."""
        authors = [
            CSLName(family=a.get("family", ""), given=a.get("given", ""))
            for a in msg.get("author", [])
            if isinstance(a, dict)
        ]
        year: int | None = None
        issued = msg.get("issued")
        parts = issued.get("date-parts") if isinstance(issued, dict) else None
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
        return cls(
            id=item_id,
            type=msg.get("type", "article-journal"),
            author=authors,
            issued_year=year,
            title=str(msg.get("title", "")),
            container_title=str(msg.get("container-title", "")),
            volume=str(msg.get("volume", "")),
            issue=str(msg.get("issue", "")),
            page=str(msg.get("page", "")),
            publisher=str(msg.get("publisher", "")),
            doi=str(msg.get("DOI", msg.get("doi", ""))),
            url=str(msg.get("URL", msg.get("url", ""))),
        )
