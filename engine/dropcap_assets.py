"""Drop-cap asset diagnostics for illuminated image initials."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any


class DropcapAssetError(RuntimeError):
    """Raised when a drop-cap asset cannot be inspected safely."""


def _read_png_chunks(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DropcapAssetError(f"not a PNG file: {path}")
    offset = 8
    ihdr: dict[str, Any] | None = None
    idat = bytearray()
    while offset < len(data):
        if offset + 8 > len(data):
            raise DropcapAssetError(f"truncated PNG chunk header: {path}")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        if payload_end + 4 > len(data):
            raise DropcapAssetError(f"truncated PNG chunk payload: {path}")
        payload = data[payload_start:payload_end]
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            ihdr = {
                "width": width,
                "height": height,
                "bit_depth": bit_depth,
                "color_type": color_type,
                "compression": compression,
                "filter_method": filter_method,
                "interlace": interlace,
            }
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
        offset = payload_end + 4
    if ihdr is None:
        raise DropcapAssetError(f"missing PNG IHDR: {path}")
    return ihdr, bytes(idat)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_scanlines(raw: bytes, *, width: int, height: int, bytes_per_pixel: int) -> list[bytes]:
    stride = width * bytes_per_pixel
    expected = height * (stride + 1)
    if len(raw) < expected:
        raise DropcapAssetError("decompressed PNG data shorter than expected")
    rows: list[bytes] = []
    previous = bytearray(stride)
    pos = 0
    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        current = bytearray(raw[pos : pos + stride])
        pos += stride
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(stride):
                left = current[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                current[i] = (current[i] + left) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                current[i] = (current[i] + previous[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = current[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = previous[i]
                current[i] = (current[i] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = current[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = previous[i]
                upper_left = previous[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                current[i] = (current[i] + _paeth(left, up, upper_left)) & 0xFF
        else:
            raise DropcapAssetError(f"unsupported PNG filter type: {filter_type}")
        rows.append(bytes(current))
        previous = current
    return rows


def analyze_dropcap_alpha_bounds(path: str | Path, *, alpha_threshold: int = 0) -> dict[str, Any]:
    """Inspect an RGBA PNG and report visible-alpha bounds and transparent margins.

    The crop box is `left,top,right,bottom` with right/bottom exclusive, matching
    common image-processing crop conventions.
    """

    png = Path(path)
    ihdr, idat = _read_png_chunks(png)
    if ihdr["bit_depth"] != 8 or ihdr["color_type"] != 6 or ihdr["interlace"] != 0:
        raise DropcapAssetError(
            "dropcap alpha diagnostics currently require non-interlaced 8-bit RGBA PNG assets"
        )
    width = ihdr["width"]
    height = ihdr["height"]
    if alpha_threshold < 0 or alpha_threshold > 255:
        raise DropcapAssetError("alpha_threshold must be between 0 and 255")
    rows = _unfilter_scanlines(zlib.decompress(idat), width=width, height=height, bytes_per_pixel=4)

    visible: list[tuple[int, int]] = []
    for y, row in enumerate(rows):
        for x in range(width):
            if row[x * 4 + 3] > alpha_threshold:
                visible.append((x, y))

    if not visible:
        return {
            "schema_version": "dropcap_alpha_bounds_v1",
            "status": "empty_alpha",
            "path": str(png),
            "width_px": width,
            "height_px": height,
            "alpha_threshold": alpha_threshold,
            "needs_crop_attention": True,
        }

    left = min(x for x, _ in visible)
    right = max(x for x, _ in visible)
    top = min(y for _, y in visible)
    bottom = max(y for _, y in visible)
    visible_width = right - left + 1
    visible_height = bottom - top + 1
    margins = {
        "left": left,
        "right": width - right - 1,
        "top": top,
        "bottom": height - bottom - 1,
    }
    margin_fraction = {
        key: round(value / (width if key in {"left", "right"} else height), 4)
        for key, value in margins.items()
    }
    return {
        "schema_version": "dropcap_alpha_bounds_v1",
        "status": "ok",
        "path": str(png),
        "width_px": width,
        "height_px": height,
        "alpha_threshold": alpha_threshold,
        "alpha_bbox_px": {"left": left, "top": top, "right": right, "bottom": bottom},
        "visible_width_px": visible_width,
        "visible_height_px": visible_height,
        "transparent_margins_px": margins,
        "transparent_margins_fraction": margin_fraction,
        "recommended_crop_box_px": f"{left},{top},{right + 1},{bottom + 1}",
        "needs_crop_attention": max(margin_fraction.values()) >= 0.08,
    }


def main_json(path: str | Path) -> str:
    return json.dumps(analyze_dropcap_alpha_bounds(path), indent=2, sort_keys=True) + "\n"
