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


# ---------------------------------------------------------------------------
# Contact-sheet comparison (2026-09-28)
#
# The regression method for multi-pass builds: render the same work before and
# after a change, and compare one thumbnail contact sheet per PDF pixel for pixel
# (Luis-ruled 2026-09-28: "don't compare every page, do a contact sheet for
# efficiency"; saved to the repo the same night). Identical sheets are the pass
# condition; a differing sheet gets a third sheet with the changed cells outlined
# in red, so the change can be looked at rather than hunted for.
# ---------------------------------------------------------------------------

CONTACT_COLUMNS = 16
CONTACT_THUMB_WIDTH = 96
CONTACT_PAD = 4


def contact_sheet_image(pdf_path: str | Path, *, columns: int = CONTACT_COLUMNS, thumb_width: int = CONTACT_THUMB_WIDTH):
    """Every page of ``pdf_path`` as one thumbnail grid (a PIL image).

    Returns ``(image, page_count, thumb_height)``. Thumbnails are scaled from the
    first page's width; cells are separated by a grey gutter.
    """
    import fitz
    from PIL import Image

    doc = fitz.open(str(pdf_path))
    try:
        first = doc[0].rect
        scale = thumb_width / first.width
        thumb_height = int(round(first.height * scale))
        rows = -(-doc.page_count // columns)
        sheet = Image.new(
            "RGB",
            (columns * (thumb_width + CONTACT_PAD) + CONTACT_PAD, rows * (thumb_height + CONTACT_PAD) + CONTACT_PAD),
            (90, 90, 90),
        )
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            r, c = divmod(i, columns)
            sheet.paste(img, (CONTACT_PAD + c * (thumb_width + CONTACT_PAD), CONTACT_PAD + r * (thumb_height + CONTACT_PAD)))
        return sheet, doc.page_count, thumb_height
    finally:
        doc.close()


def compare_contact_sheets(
    baseline_pdf: str | Path,
    candidate_pdf: str | Path,
    *,
    output_dir: str | Path,
    label: str,
    columns: int = CONTACT_COLUMNS,
    thumb_width: int = CONTACT_THUMB_WIDTH,
) -> dict:
    """Compare two PDFs by contact sheet; write the sheets; report what differs.

    Writes ``<label>_baseline.png`` and ``<label>_candidate.png`` into
    ``output_dir``, plus ``<label>_diff.png`` (the candidate with every differing
    cell outlined in red) when they differ. ``identical`` is true only when the
    page counts agree and the two sheets are pixel-identical.
    """
    from PIL import ImageChops, ImageDraw

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sa, na, th = contact_sheet_image(baseline_pdf, columns=columns, thumb_width=thumb_width)
    sb, nb, _ = contact_sheet_image(candidate_pdf, columns=columns, thumb_width=thumb_width)
    result = {
        "label": label,
        "baseline_pdf": str(baseline_pdf),
        "candidate_pdf": str(candidate_pdf),
        "baseline_pages": na,
        "candidate_pages": nb,
        "baseline_sheet": str(out / f"{label}_baseline.png"),
        "candidate_sheet": str(out / f"{label}_candidate.png"),
        "differing_pages": [],
        "identical": False,
    }
    sa.save(result["baseline_sheet"])
    sb.save(result["candidate_sheet"])
    if na != nb or sa.size != sb.size:
        return result
    diff = ImageChops.difference(sa, sb)
    if diff.getbbox() is None:
        result["identical"] = True
        return result
    marked = sb.copy()
    draw = ImageDraw.Draw(marked)
    for i in range(na):
        r, c = divmod(i, columns)
        x0 = CONTACT_PAD + c * (thumb_width + CONTACT_PAD)
        y0 = CONTACT_PAD + r * (th + CONTACT_PAD)
        box = (x0, y0, x0 + thumb_width, y0 + th)
        if diff.crop(box).getbbox() is not None:
            result["differing_pages"].append(i + 1)
            draw.rectangle(box, outline=(255, 0, 0), width=3)
    result["diff_sheet"] = str(out / f"{label}_diff.png")
    marked.save(result["diff_sheet"])
    edge_only = edge_only_pages(baseline_pdf, candidate_pdf, result["differing_pages"])
    result["edge_only_pages"] = edge_only
    result["substantive_pages"] = [p for p in result["differing_pages"] if p not in edge_only]
    return result


def _drawing_shape(page) -> list[tuple]:
    """Vector drawings on a page, as (kind, rounded rect, fill, stroke) — so a moved
    or recoloured rule is never mistaken for an edge-only difference."""
    shape = []
    for d in page.get_drawings():
        r = d.get("rect")
        rect = tuple(round(v, 1) for v in (r.x0, r.y0, r.x1, r.y1)) if r is not None else None
        shape.append((d.get("type"), rect, d.get("fill"), d.get("color")))
    return shape


def edge_only_pages(baseline_pdf: str | Path, candidate_pdf: str | Path, pages: list[int]) -> list[int]:
    """Of ``pages`` (1-based), those whose difference cannot be in the content.

    A page qualifies when both renders carry the same text, the same vector
    drawings, and the same images — identical decoded image data (MuPDF's
    digest) at identical placements. What
    remains is rasterization: an image embedded through a Form XObject (the
    lossless image bake, engine/image_bake.py) moves the anti-aliasing of its
    outermost edge pixels at some scales. Accepted and marked by keeper ruling
    01a0eb4f-849e-7e9f-979d-b666c8db0d9b (2026-09-28): "I'll accept it. But
    mark it." Callers report these pages as marked, never silently.
    """
    import fitz

    a, b = fitz.open(str(baseline_pdf)), fitz.open(str(candidate_pdf))
    try:
        found = []
        for number in pages:
            pa, pb = a[number - 1], b[number - 1]
            if pa.get_text() != pb.get_text():
                continue
            ia, ib = pa.get_image_info(hashes=True), pb.get_image_info(hashes=True)
            if len(ia) != len(ib) or not ia:
                continue
            same = all(
                x.get("digest") == y.get("digest")
                and [round(v, 2) for v in x["bbox"]] == [round(v, 2) for v in y["bbox"]]
                for x, y in zip(ia, ib)
            )
            if same and _drawing_shape(pa) == _drawing_shape(pb):
                found.append(number)
        return found
    finally:
        a.close()
        b.close()
