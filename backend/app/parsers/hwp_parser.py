"""Legacy HWP parser (research.md §2.2, §2.5.4).

Primary path: convert HWP → HWPX via hwpx-skill's convert_hwp.py, then delegate
to the HWPX parser (records original_format='hwp'). The HWP→HWPX conversion is
also the basis for the writer path (download as .hwpx).
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
            "convert_hwp.py 를 찾을 수 없습니다. hwpx-skill submodule을 초기화하세요."
        )
    out_path = hwp_path.with_suffix(".hwpx")
    # convert_hwp.py CLI: `input -o output` (see vendor/hwpx-skill/scripts).
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(script), str(hwp_path), "-o", str(out_path)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(VENDOR_DIR),
    )
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"HWP→HWPX 변환 실패: {proc.stderr[:500]}")
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
