"""HWPX writer via hwpx-skill clone_form + fix_namespaces (research.md §2.5.3).

Serialises accepted patches to a replacements map, calls the skill's
clone_form.py, and ALWAYS runs fix_namespaces.py afterward (mandatory per the
skill's operating rules — skipping it can corrupt the file in Hangul).
Default output mode is 'annotated' (HWPX tracked-changes compatibility is
unconfirmed, research.md §2.5.6).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from app.parsers.hwpx_parser import VENDOR_DIR, HwpxSkillMissingError
from app.writers.base import OutputMode, Patch


def _script(name: str) -> Path:
    p = VENDOR_DIR / "scripts" / name
    if not p.exists():
        raise HwpxSkillMissingError(f"hwpx-skill '{name}' 미발견 — submodule을 초기화하세요.")
    return p


def _patches_to_replacements(patches: list[Patch]) -> dict[str, str]:
    """Serialise patches to hwpx-skill's replacement map: {"old text": "new text"}.

    clone_form.py loads this JSON as a dict and applies find->replace over the
    document text (see vendor/hwpx-skill/clone_form.py).
    """
    out: dict[str, str] = {}
    for p in patches:
        if p.kind in {"reference_replace", "doi_insert"} and p.before:
            out[p.before] = p.after
        elif p.kind == "citation_comment" and p.before:
            out[p.before] = f"{p.before}  [{p.comment}]"
    return out


class HwpxWriter:
    def apply(
        self,
        data: bytes,
        patches: list[Patch],
        mode: OutputMode = "annotated",
    ) -> bytes:
        clone = _script("clone_form.py")
        fix_ns = _script("fix_namespaces.py")

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "input.hwpx"
            out = tdp / "output.hwpx"
            mapping = tdp / "replacements.json"
            src.write_bytes(data)
            mapping.write_text(
                json.dumps(_patches_to_replacements(patches), ensure_ascii=False),
                encoding="utf-8",
            )

            clone_proc = subprocess.run(  # noqa: S603
                [
                    sys.executable,
                    str(clone),
                    str(src),
                    str(out),
                    "--replacements",
                    str(mapping),
                ],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(VENDOR_DIR),
            )
            if clone_proc.returncode != 0 or not out.exists():
                raise RuntimeError(f"clone_form 실패: {clone_proc.stderr[:500]}")

            # MANDATORY post-step.
            fix_proc = subprocess.run(  # noqa: S603
                [sys.executable, str(fix_ns), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(VENDOR_DIR),
            )
            if fix_proc.returncode != 0:
                raise RuntimeError(f"fix_namespaces 실패: {fix_proc.stderr[:500]}")

            return out.read_bytes()
