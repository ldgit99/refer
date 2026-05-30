"""Legacy HWP parser.

Primary path: convert binary HWP to HWPX via hwpx-skill's ``convert_hwp.py``,
then delegate to the HWPX parser while preserving ``original_format='hwp'``.
The writer path also returns HWP uploads as HWPX downloads.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from app.parsers.base import ParsedDocument
from app.parsers.hwpx_parser import VENDOR_DIR, HwpxSkillMissingError, parse_hwpx


def _convert_hwp_to_hwpx(hwp_path: Path) -> Path:
    script = VENDOR_DIR / "scripts" / "convert_hwp.py"
    if not script.exists():
        raise HwpxSkillMissingError(
            "HWP conversion is unavailable because hwpx-skill/scripts/convert_hwp.py "
            "is missing. Initialize the submodule or use the Docker/Fly deployment."
        )
    out_path = hwp_path.with_suffix(".hwpx")
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(script), str(hwp_path), "-o", str(out_path)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(VENDOR_DIR),
    )
    if proc.returncode != 0 or not out_path.exists():
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise RuntimeError(
            "HWP to HWPX conversion failed. HWP support requires the hwpx-skill "
            f"conversion dependencies in the runtime. Detail: {detail}"
        )
    return out_path


def parse_hwp(data: bytes) -> ParsedDocument:
    with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as tmp:
        tmp.write(data)
        hwp_path = Path(tmp.name)
    hwpx_path: Path | None = None
    try:
        hwpx_path = _convert_hwp_to_hwpx(hwp_path)
        return parse_hwpx(hwpx_path.read_bytes(), original_format="hwp")
    finally:
        hwp_path.unlink(missing_ok=True)
        if hwpx_path is not None:
            hwpx_path.unlink(missing_ok=True)
