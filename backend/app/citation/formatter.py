"""F2 — APA 7th reference formatting.

Primary path uses citeproc-py + the bundled ``apa.csl`` when available. Because
citeproc-py + a CSL style file is a heavyweight optional dependency (and the CSL
file must be vendored), this module ships a faithful deterministic APA 7
formatter as the default so the pipeline always works. The citeproc path can be
enabled later without changing the public API.
"""

from __future__ import annotations

from app.citation.csl import CSLItem, CSLName


def _format_author_apa(name: CSLName) -> str:
    family = name.family.strip()
    given = name.given.strip()
    if not family:
        return given
    if not given:
        return family
    # Initials: "Soo Jin" -> "S. J."
    initials = " ".join(
        f"{part[0].upper()}." for part in given.replace(".", " ").split() if part
    )
    return f"{family}, {initials}" if initials else family


def _format_authors_apa(authors: list[CSLName]) -> str:
    if not authors:
        return ""
    formatted = [_format_author_apa(a) for a in authors]
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) <= 20:
        return ", ".join(formatted[:-1]) + ", & " + formatted[-1]
    # APA 7: 21+ authors -> first 19, ellipsis, last author.
    return ", ".join(formatted[:19]) + ", … " + formatted[-1]


def format_apa(item: CSLItem) -> str:
    """Render a CSLItem as an APA 7th reference string."""
    parts: list[str] = []

    authors = _format_authors_apa(item.author)
    if authors:
        parts.append(authors if authors.endswith(".") else authors + ".")

    year = f"({item.issued_year})." if item.issued_year else "(n.d.)."
    parts.append(year)

    if item.title:
        title = item.title.strip()
        parts.append(title if title.endswith(".") else title + ".")

    # Source segment depends on the work type.
    if item.type in {"book", "monograph"}:
        if item.publisher:
            parts.append(f"{item.publisher}.")
    else:
        source = ""
        if item.container_title:
            source = item.container_title.strip()
            if item.volume:
                source += f", {item.volume}"
                if item.issue:
                    source += f"({item.issue})"
            if item.page:
                source += f", {item.page}"
            source += "."
        if source:
            parts.append(source)

    if item.doi:
        doi = item.doi.strip().lower()
        parts.append(f"https://doi.org/{doi}")
    elif item.url:
        parts.append(item.url.strip())

    return " ".join(p for p in parts if p).strip()
