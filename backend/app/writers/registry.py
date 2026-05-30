"""Format -> Writer dispatch."""

from __future__ import annotations

from app.writers.base import OutputMode, Patch
from app.writers.docx_writer import DocxWriter


def get_writer(original_format: str):
    if original_format == "docx":
        return DocxWriter()
    if original_format == "hwpx":
        from app.writers.hwpx_writer import HwpxWriter

        return HwpxWriter()
    if original_format == "hwp":
        from app.writers.hwp_writer import HwpWriter

        return HwpWriter()
    raise ValueError(f"'{original_format}' 포맷 writer는 아직 지원하지 않습니다.")


def apply_patches(
    data: bytes,
    original_format: str,
    patches: list[Patch],
    mode: OutputMode = "tracked",
) -> bytes:
    writer = get_writer(original_format)
    return writer.apply(data, patches, mode)
