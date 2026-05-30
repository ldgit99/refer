"""HWPX parser via the vendored jkf87/hwpx-skill (research.md §2.3).

The skill is a git submodule at backend/vendor/hwpx-skill. We call its
text-extraction entry point in a subprocess and normalise the output into a
ParsedDocument. If the submodule is absent, a built-in ZIP/XML fallback runs.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import zipfile
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

from app.parsers.base import ParsedDocument, build_document

VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor" / "hwpx-skill"


class HwpxSkillMissingError(RuntimeError):
    pass


def _skill_script(name: str) -> Path:
    for candidate in (VENDOR_DIR / "scripts" / name, VENDOR_DIR / name):
        if candidate.exists():
            return candidate
    raise HwpxSkillMissingError(
        f"hwpx-skill 스크립트 '{name}'를 찾을 수 없습니다. "
        "`git submodule update --init backend/vendor/hwpx-skill` 를 실행하세요."
    )


def _extract_text_via_skill(path: Path) -> str:
    script = _skill_script("text_extract.py")
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(script), str(path), "--format", "markdown"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(VENDOR_DIR),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"hwpx text_extract 실패: {proc.stderr[:500]}")
    return proc.stdout


def _fallback_extract(path: Path) -> str:
    """Built-in HWPX text extraction (ZIP + section XML) as a safety net.

    HWPX is a ZIP of XML; body text usually lives in ``Contents/section*.xml``
    as ``hp:t`` nodes, but real files may use namespaces, table-cell nesting,
    line-break/control nodes, or plain ``t`` local names. ElementTree local-name
    matching is more robust than a raw regex and keeps table text available.
    """
    paragraphs: list[str] = []

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    def paragraph_text(node: ET.Element) -> str:
        parts: list[str] = []
        for child in node.iter():
            name = local_name(child.tag)
            if name == "t" and child.text:
                parts.append(child.text)
            elif name in {"lineBreak", "br"}:
                parts.append("\n")
        return unescape("".join(parts)).strip()

    with zipfile.ZipFile(path) as zf:
        names = sorted(n for n in zf.namelist() if re.search(r"section\d+\.xml$", n))
        for n in names:
            raw = zf.read(n)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                xml = raw.decode("utf-8", errors="ignore")
                for m in re.finditer(r"<(?:\w+:)?t[^>]*>(.*?)</(?:\w+:)?t>", xml, flags=re.DOTALL):
                    frag = unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
                    if frag:
                        paragraphs.append(frag)
                continue

            for node in root.iter():
                if local_name(node.tag) not in {"p", "subList"}:
                    continue
                text = paragraph_text(node)
                if text:
                    paragraphs.extend(line for line in text.splitlines() if line.strip())

    return "\n".join(paragraphs)


def parse_hwpx(data: bytes, original_format: str = "hwpx") -> ParsedDocument:
    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        try:
            text = _extract_text_via_skill(tmp_path)
        except (HwpxSkillMissingError, RuntimeError):
            text = _fallback_extract(tmp_path)
        raw_paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
        if not raw_paragraphs:
            raise RuntimeError("HWPX 텍스트를 추출하지 못했습니다.")
        return build_document(raw_paragraphs, original_format=original_format)
    finally:
        tmp_path.unlink(missing_ok=True)
