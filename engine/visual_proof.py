"""Visual proof/contact-sheet helpers for rendered Optical Foundry PDFs."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable


Rasterizer = Callable[[Path, Path], tuple[int, list[Path]]]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pdf_page_count(pdf_path: Path) -> int:
    info = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True)
    m = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
    if not m:
        raise RuntimeError(f"could not determine PDF page count: {pdf_path}")
    return int(m.group(1))


def rasterize_pdf_pages(
    pdf_path: Path,
    pages_dir: Path,
    *,
    max_pages: int = 12,
    dpi: int = 120,
) -> tuple[int, list[Path]]:
    """Rasterize the first `max_pages` pages of a PDF to PNGs with pdftoppm.

    Returns `(total_pdf_pages, rasterized_page_paths)`.
    """

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    pages_dir = Path(pages_dir)
    pages_dir.mkdir(parents=True, exist_ok=True)

    total_pages = _pdf_page_count(pdf_path)
    pages_to_render = min(max(1, max_pages), total_pages)
    prefix = pages_dir / pdf_path.stem
    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-r",
            str(dpi),
            "-f",
            "1",
            "-l",
            str(pages_to_render),
            str(pdf_path),
            str(prefix),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    page_images = sorted(pages_dir.glob(f"{pdf_path.stem}-*.png"))[:pages_to_render]
    if len(page_images) != pages_to_render:
        raise RuntimeError(
            f"pdftoppm rendered {len(page_images)} pages, expected {pages_to_render}: {pdf_path}"
        )
    return total_pages, page_images


def _relative_href(path: Path, *, relative_to: Path) -> str:
    return os.path.relpath(path.resolve(), start=relative_to.resolve()).replace(os.sep, "/")


def write_contact_sheet_svg(
    page_images: list[Path],
    *,
    output_svg: Path,
    title: str,
    columns: int = 3,
    thumb_width: int = 360,
) -> Path:
    """Write an SVG contact sheet with labels and linked page preview images."""

    if not page_images:
        raise ValueError("contact sheet requires at least one page image")
    if columns < 1:
        raise ValueError("columns must be >= 1")
    if thumb_width < 80:
        raise ValueError("thumb_width must be >= 80")

    output_svg = Path(output_svg)
    output_svg.parent.mkdir(parents=True, exist_ok=True)

    gap = 24
    label_height = 32
    title_height = 56
    thumb_height = int(thumb_width * 1.414)
    card_width = thumb_width
    card_height = label_height + thumb_height
    rows = (len(page_images) + columns - 1) // columns
    width = columns * card_width + (columns + 1) * gap
    height = title_height + rows * card_height + (rows + 1) * gap

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101216"/>',
        f'<text x="{gap}" y="36" fill="#f4efe6" font-family="Avenir, Helvetica, Arial, sans-serif" font-size="22" font-weight="700">{html.escape(title)}</text>',
    ]
    for index, image in enumerate(page_images, start=1):
        col = (index - 1) % columns
        row = (index - 1) // columns
        x = gap + col * (card_width + gap)
        y = title_height + gap + row * (card_height + gap)
        label = f"Page {index}"
        href = html.escape(_relative_href(Path(image), relative_to=output_svg.parent), quote=True)
        parts.extend(
            [
                f'<rect x="{x - 6}" y="{y - 6}" width="{card_width + 12}" height="{card_height + 12}" rx="10" fill="#1b1f27" stroke="#3a4150"/>',
                f'<text x="{x}" y="{y + 21}" fill="#d9c89e" font-family="Avenir, Helvetica, Arial, sans-serif" font-size="16" font-weight="700">{label}</text>',
                f'<image x="{x}" y="{y + label_height}" width="{thumb_width}" height="{thumb_height}" preserveAspectRatio="xMidYMin meet" href="{href}"/>',
            ]
        )
    parts.append("</svg>")
    output_svg.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return output_svg


def build_visual_proof(
    pdf_path: str | Path,
    *,
    output_dir: str | Path,
    max_pages: int = 12,
    columns: int = 3,
    dpi: int = 120,
    rasterizer: Callable[..., tuple[int, list[Path]]] = rasterize_pdf_pages,
) -> dict:
    """Create raster previews, a labeled contact sheet, and proof metadata for a PDF."""

    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(pdf)
    out = Path(output_dir)
    pages_dir = out / "pages"
    out.mkdir(parents=True, exist_ok=True)

    total_pages, page_images = rasterizer(pdf, pages_dir, max_pages=max_pages, dpi=dpi)
    contact_sheet = write_contact_sheet_svg(
        page_images,
        output_svg=out / "contact_sheet.svg",
        title=f"Visual proof: {pdf.name}",
        columns=columns,
    )

    proof = {
        "schema_version": "visual_proof_v1",
        "status": "ok",
        "source_pdf": str(pdf),
        "source_pdf_sha256": _sha256_file(pdf),
        "source_pdf_pages": total_pages,
        "pages_rasterized": len(page_images),
        "max_pages": max_pages,
        "dpi": dpi,
        "columns": columns,
        "page_images": [str(p) for p in page_images],
        "contact_sheet_svg": str(contact_sheet),
    }
    metadata_path = out / "visual_proof.json"
    proof["metadata_path"] = str(metadata_path)
    metadata_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return proof
