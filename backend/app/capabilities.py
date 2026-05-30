"""Runtime capability checks for optional document-format features."""

from __future__ import annotations

import shutil
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor" / "hwpx-skill"


def _script_exists(name: str) -> bool:
    return (VENDOR_DIR / "scripts" / name).exists() or (VENDOR_DIR / name).exists()


def document_capabilities() -> dict[str, object]:
    """Return feature availability without executing heavyweight converters."""
    hwpx_text = _script_exists("text_extract.py")
    hwpx_write = _script_exists("clone_form.py") and _script_exists("fix_namespaces.py")
    hwp_convert = _script_exists("convert_hwp.py")
    libreoffice = bool(shutil.which("soffice") or shutil.which("libreoffice"))

    return {
        "docx": {"parse": True, "write": True, "download_format": "docx"},
        "hwpx": {
            "parse": True,
            "write": hwpx_write,
            "download_format": "hwpx",
            "skill_available": VENDOR_DIR.exists(),
            "text_extract_script": hwpx_text,
            "zip_xml_fallback": True,
        },
        "hwp": {
            "parse": hwp_convert,
            "write": hwp_convert and hwpx_write,
            "download_format": "hwpx",
            "convert_hwp_script": hwp_convert,
            "native_hwp_export": libreoffice,
        },
    }
