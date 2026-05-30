"""HWP writer (research.md §2.5.4).

Primary path: apply patches via the HWPX writer and return .hwpx bytes (the user
agreed to the extension change at upload time). LibreOffice round-trip back to
.hwp is an experimental fallback only and requires soffice in the image.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.writers.base import OutputMode, Patch
from app.writers.hwpx_writer import HwpxWriter


class HwpWriter:
    """Returns HWPX bytes (download is .hwpx). ``produces_format`` advertises it."""

    produces_format = "hwpx"

    def apply(
        self,
        data: bytes,
        patches: list[Patch],
        mode: OutputMode = "annotated",
    ) -> bytes:
        from app.parsers.hwp_parser import _convert_hwp_to_hwpx

        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as tmp:
            tmp.write(data)
            hwp_path = Path(tmp.name)
        try:
            hwpx_path = _convert_hwp_to_hwpx(hwp_path)
            try:
                return HwpxWriter().apply(hwpx_path.read_bytes(), patches, mode)
            finally:
                hwpx_path.unlink(missing_ok=True)
        finally:
            hwp_path.unlink(missing_ok=True)


def libreoffice_convert(hwpx_bytes: bytes, target_ext: str = "hwp") -> bytes:
    """Experimental: convert HWPX→HWP via LibreOffice headless (image only)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice(soffice)가 설치되어 있지 않습니다.")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        src = tdp / "in.hwpx"
        src.write_bytes(hwpx_bytes)
        proc = subprocess.run(  # noqa: S603
            [soffice, "--headless", "--convert-to", target_ext, "--outdir", str(tdp), str(src)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        out = tdp / f"in.{target_ext}"
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"LibreOffice 변환 실패: {proc.stderr[:500]}")
        return out.read_bytes()
