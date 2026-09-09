"""Booklet/signature PDF imposition for Optical Foundry.

This module imposes already-rendered single-page PDFs into printer sheets for
folded signatures. The first supported production lane is half-letter pages on
letter sheets: two portrait pages per landscape sheet side, ordered as booklet
folios per signature.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import os
import re
import shutil
import subprocess

from engine.page_size import normalize_page_size


POINTS_PER_INCH = 72.0
PAGE_SIZE_INCHES: dict[str, tuple[float, float]] = {
    "letter": (8.5, 11.0),
    "half_letter": (5.5, 8.5),
    "a4": (8.27, 11.69),
    "a5": (5.83, 8.27),
    # sheet only in practice: two letter pages side by side on a landscape 11 x 17
    "tabloid": (11.0, 17.0),
}
DUPLEX_ALIASES = {
    "short_edge": "short_edge",
    "short-edge": "short_edge",
    "short edge": "short_edge",
    "short": "short_edge",
    "long_edge": "long_edge",
    "long-edge": "long_edge",
    "long edge": "long_edge",
    "long": "long_edge",
}


class ImpositionError(ValueError):
    """Raised when an imposition request is malformed or unsupported."""


@dataclass(frozen=True)
class SheetSide:
    name: str
    pages: list[int | None]
    output_page: int
    rotate_180: bool = False


@dataclass(frozen=True)
class SheetPlan:
    sheet_index: int
    sides: list[SheetSide]


@dataclass(frozen=True)
class SignaturePlan:
    signature_index: int
    source_start_page: int
    source_end_page: int
    padded_start_page: int
    padded_end_page: int
    sheets: list[SheetPlan]


@dataclass(frozen=True)
class BookletImpositionPlan:
    input_pages: int
    signature_size: int
    padded_pages: int
    blank_count: int
    signatures: list[SignaturePlan]


@dataclass(frozen=True)
class ImpositionResult:
    output_pdf: Path
    mapping_json: Path
    tex_path: Path
    input_pages: int
    output_pages: int
    padded_pages: int
    blank_count: int


def normalize_duplex_mode(value: str) -> str:
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    normalized = DUPLEX_ALIASES.get(key)
    if normalized is None:
        raise ImpositionError("duplex mode must be short-edge or long-edge")
    return normalized


def normalize_signature_size(value: int | str) -> int:
    try:
        size = int(value)
    except Exception as exc:  # noqa: BLE001 - normalize to user-facing error
        raise ImpositionError("signature size must be an integer multiple of 4") from exc
    if size <= 0 or size % 4 != 0:
        raise ImpositionError("signature size must be a positive multiple of 4")
    return size


def build_booklet_signature_plan(
    *,
    total_pages: int,
    signature_size: int,
    duplex_mode: str = "short_edge",
) -> BookletImpositionPlan:
    """Return the folio page map for booklet signatures.

    Page numbers are 1-based input PDF pages. ``None`` denotes an intentional
    blank slot introduced by signature padding.
    """

    if total_pages <= 0:
        raise ImpositionError("input PDF must contain at least one page")
    sig_size = normalize_signature_size(signature_size)
    duplex = normalize_duplex_mode(duplex_mode)
    signature_count = math.ceil(total_pages / sig_size)
    padded_pages = signature_count * sig_size
    blank_count = padded_pages - total_pages
    pages: list[int | None] = [*range(1, total_pages + 1), *([None] * blank_count)]
    signatures: list[SignaturePlan] = []
    output_page = 1

    for sig_idx in range(signature_count):
        start = sig_idx * sig_size
        signature_pages = pages[start:start + sig_size]
        source_start = start + 1
        source_end = min(start + sig_size, total_pages)
        sheets: list[SheetPlan] = []
        for sheet_idx in range(sig_size // 4):
            front = [signature_pages[sig_size - 1 - (2 * sheet_idx)], signature_pages[2 * sheet_idx]]
            back = [signature_pages[(2 * sheet_idx) + 1], signature_pages[sig_size - 2 - (2 * sheet_idx)]]
            sheets.append(
                SheetPlan(
                    sheet_index=sheet_idx + 1,
                    sides=[
                        SheetSide("front", front, output_page, rotate_180=False),
                        SheetSide("back", back, output_page + 1, rotate_180=(duplex == "long_edge")),
                    ],
                )
            )
            output_page += 2
        signatures.append(
            SignaturePlan(
                signature_index=sig_idx + 1,
                source_start_page=source_start,
                source_end_page=source_end,
                padded_start_page=start + 1,
                padded_end_page=start + sig_size,
                sheets=sheets,
            )
        )

    return BookletImpositionPlan(
        input_pages=total_pages,
        signature_size=sig_size,
        padded_pages=padded_pages,
        blank_count=blank_count,
        signatures=signatures,
    )


def impose_pdf(
    input_pdf: str | Path,
    *,
    output: str | Path,
    page_size: str,
    sheet_size: str,
    signature_size: int | str,
    duplex_mode: str,
    gutter_bias_mm: float = 0.0,
) -> ImpositionResult:
    """Impose a PDF into booklet/signature sheet sides.

    ``output`` may be either a directory or a final ``.pdf`` path. A JSON page
    map is written beside the imposed PDF.

    ``gutter_bias_mm`` (Luis-ruled 2026-07-27, plate sheets) nudges each imposed
    page OUTWARD toward its outer sheet edge by this amount, so any printer
    unprintable/fade shortfall accumulates in the CENTER (spine/gutter, hidden in
    the bind) rather than at the trimmed fore-edges. Default 0 (pure-text sheets).
    """

    input_path = Path(input_pdf).expanduser().resolve()
    if not input_path.exists():
        raise ImpositionError(f"input PDF not found: {input_path}")
    page = normalize_page_size(page_size, scope="imposition.page_size")
    sheet = normalize_page_size(sheet_size, scope="imposition.sheet_size")
    sig_size = normalize_signature_size(signature_size)
    duplex = normalize_duplex_mode(duplex_mode)
    _validate_sheet_pair(page, sheet)

    output_path = Path(output).expanduser()
    if output_path.suffix.lower() == ".pdf":
        output_pdf = output_path.resolve()
        out_dir = output_pdf.parent
    else:
        out_dir = output_path.resolve()
        output_pdf = out_dir / f"{input_path.stem}.imposed-{page}-on-{sheet}-sig{sig_size}-{duplex}.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_info = inspect_pdf(input_path)
    _validate_pdf_page_size(pdf_info, page, context="input PDF")
    plan = build_booklet_signature_plan(
        total_pages=pdf_info["pages"],
        signature_size=sig_size,
        duplex_mode=duplex,
    )

    build_dir = out_dir / f".{output_pdf.stem}.build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    build_input = build_dir / "input.pdf"
    shutil.copy2(input_path, build_input)
    tex_path = build_dir / "impose.tex"
    tex_path.write_text(_render_imposition_tex(
        plan, page_size=page, sheet_size=sheet, input_name=build_input.name,
        gutter_bias_mm=gutter_bias_mm))

    xelatex = os.environ.get("XELATEX") or shutil.which("xelatex") or "/Library/TeX/texbin/xelatex"
    proc = subprocess.run(
        [
            xelatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            tex_path.name,
        ],
        cwd=build_dir,
        text=True,
        capture_output=True,
        timeout=240,
    )
    built_pdf = tex_path.with_suffix(".pdf")
    if proc.returncode != 0 or not built_pdf.exists():
        log = (tex_path.with_suffix(".log").read_text(errors="replace") if tex_path.with_suffix(".log").exists() else "")
        raise ImpositionError(f"xelatex imposition failed: {proc.stderr or proc.stdout or log[-1200:]}")
    shutil.copy2(built_pdf, output_pdf)

    mapping_path = output_pdf.with_suffix(".imposition.json")
    mapping_path.write_text(json.dumps(_mapping_payload(plan, input_path, output_pdf, page, sheet, duplex), indent=2) + "\n")
    output_info = inspect_pdf(output_pdf)
    _validate_pdf_page_size(output_info, sheet, context="imposed output", landscape=True)
    return ImpositionResult(
        output_pdf=output_pdf,
        mapping_json=mapping_path,
        tex_path=tex_path,
        input_pages=plan.input_pages,
        output_pages=output_info["pages"],
        padded_pages=plan.padded_pages,
        blank_count=plan.blank_count,
    )


def inspect_pdf(path: Path) -> dict[str, object]:
    """Return page count and every page's dimensions using pdfinfo."""

    proc = subprocess.run(["pdfinfo", "-f", "1", "-l", "9999", "-box", str(path)], text=True, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise ImpositionError(f"pdfinfo failed for {path}: {proc.stderr.strip()}")
    pages = re.search(r"^Pages:\s+(\d+)", proc.stdout, re.MULTILINE)
    if not pages:
        raise ImpositionError(f"could not inspect PDF page count: {path}")
    page_count = int(pages.group(1))
    page_sizes: list[dict[str, float | int]] = []
    for match in re.finditer(r"^Page\s+(\d+)\s+size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts", proc.stdout, re.MULTILINE):
        page_sizes.append(
            {
                "page": int(match.group(1)),
                "width_pt": float(match.group(2)),
                "height_pt": float(match.group(3)),
            }
        )
    if len(page_sizes) != page_count:
        raise ImpositionError(f"could not inspect every PDF page size for {path}: found {len(page_sizes)} of {page_count}")
    first = page_sizes[0]
    return {
        "pages": page_count,
        "width_pt": first["width_pt"],
        "height_pt": first["height_pt"],
        "page_sizes": page_sizes,
    }


def _validate_sheet_pair(page_size: str, sheet_size: str) -> None:
    page_w, page_h = PAGE_SIZE_INCHES[page_size]
    sheet_w, sheet_h = PAGE_SIZE_INCHES[sheet_size]
    landscape_w, landscape_h = max(sheet_w, sheet_h), min(sheet_w, sheet_h)
    if not (_close(landscape_w, 2 * page_w, tolerance=0.08) and _close(landscape_h, page_h, tolerance=0.08)):
        raise ImpositionError(
            f"unsupported imposition pair: two {page_size} pages must fit exactly on one landscape {sheet_size} sheet"
        )


def _validate_pdf_page_size(pdf_info: dict[str, object], page_size: str, *, context: str, landscape: bool = False) -> None:
    expected_w, expected_h = PAGE_SIZE_INCHES[page_size]
    if landscape:
        expected_w, expected_h = max(expected_w, expected_h), min(expected_w, expected_h)
    page_sizes = pdf_info.get("page_sizes") or [
        {"page": 1, "width_pt": pdf_info["width_pt"], "height_pt": pdf_info["height_pt"]}
    ]
    bad_pages: list[str] = []
    for entry in page_sizes:  # type: ignore[assignment]
        width = float(entry["width_pt"]) / POINTS_PER_INCH
        height = float(entry["height_pt"]) / POINTS_PER_INCH
        if not (_close(width, expected_w, tolerance=0.04) and _close(height, expected_h, tolerance=0.04)):
            bad_pages.append(f"p{entry['page']}={width:.2f}×{height:.2f}in")
    if bad_pages:
        preview = ", ".join(bad_pages[:8])
        if len(bad_pages) > 8:
            preview += f", … +{len(bad_pages) - 8} more"
        raise ImpositionError(
            f"{context} has pages that do not match {expected_w:.2f}×{expected_h:.2f}in for {page_size}: {preview}"
        )


def _render_imposition_tex(plan: BookletImpositionPlan, *, page_size: str, sheet_size: str, input_name: str, gutter_bias_mm: float = 0.0) -> str:
    sheet_w, sheet_h = PAGE_SIZE_INCHES[sheet_size]
    landscape_w, landscape_h = max(sheet_w, sheet_h), min(sheet_w, sheet_h)
    bias = f"{max(0.0, float(gutter_bias_mm))}mm"
    lines = [
        r"\documentclass{article}",
        rf"\usepackage[paperwidth={landscape_w}in,paperheight={landscape_h}in,margin=0in]{{geometry}}",
        r"\usepackage{graphicx}",
        r"\pagestyle{empty}",
        r"\setlength{\parindent}{0pt}",
        # Gutter bias (plate sheets): nudge each page outward by \OFGutterBias so
        # the printer shortfall lands in the center (spine/gutter), not the
        # fore-edges. Left page shifts left, right page shifts right, opening a
        # 2*bias gap at the fold. 0mm = pure text sheets, no shift. The outward
        # overflow past the sheet edge is the fore-edge (trimmed / bleed-absorbed).
        rf"\newlength{{\OFGutterBias}}\setlength{{\OFGutterBias}}{{{bias}}}",
        r"\newcommand{\OFSlot}[1]{\begin{minipage}[c][\paperheight][c]{0.5\paperwidth}\centering #1\end{minipage}}",
        rf"\newcommand{{\OFSourcePage}}[1]{{\OFSlot{{\includegraphics[page=#1,width=\linewidth,height=\paperheight,keepaspectratio]{{{input_name}}}}}}}",
        # \strut keeps the slot at its full 0.5\paperwidth: an EMPTY minipage
        # collapses to zero width, which shifts the facing (non-blank) page to the
        # wrong half — e.g. a recto leaf paired with a leading blank printed on the
        # LEFT instead of the right (found on the single-leaf cardstock test).
        r"\newcommand{\OFBlankPage}{\OFSlot{\strut}}",
        # #1 = left page (shift left/outward), #2 = right page (shift right/outward).
        r"\newcommand{\OFSide}[2]{\noindent\hspace*{-\OFGutterBias}{#1}\hspace*{2\OFGutterBias}{#2}\newpage}",
        # Rotated (long-edge duplex): the 180 rotation flips left/right, so bias is
        # inverted inside the rotatebox to keep the physical shift outward.
        r"\newcommand{\OFRotatedSide}[2]{\noindent\rotatebox{180}{\begin{minipage}{\paperwidth}\hspace*{-\OFGutterBias}{#1}\hspace*{2\OFGutterBias}{#2}\end{minipage}}\newpage}",
        r"\begin{document}",
    ]
    for signature in plan.signatures:
        lines.append(rf"% Signature {signature.signature_index}")
        for sheet in signature.sheets:
            for side in sheet.sides:
                command = r"\OFRotatedSide" if side.rotate_180 else r"\OFSide"
                slots = [_slot_tex(page) for page in side.pages]
                lines.append(rf"% Signature {signature.signature_index}, sheet {sheet.sheet_index}, {side.name}, output page {side.output_page}")
                lines.append(rf"{command}{{{slots[0]}}}{{{slots[1]}}}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def _slot_tex(page: int | None) -> str:
    return r"\OFBlankPage" if page is None else rf"\OFSourcePage{{{page}}}"


def _mapping_payload(
    plan: BookletImpositionPlan,
    input_pdf: Path,
    output_pdf: Path,
    page_size: str,
    sheet_size: str,
    duplex_mode: str,
) -> dict[str, object]:
    signatures: list[dict[str, object]] = []
    for signature in plan.signatures:
        signatures.append(
            {
                "signature_index": signature.signature_index,
                "source_page_range": [signature.source_start_page, signature.source_end_page],
                "padded_page_range": [signature.padded_start_page, signature.padded_end_page],
                "sheets": [
                    {
                        "sheet_index": sheet.sheet_index,
                        "front": _side_payload(sheet.sides[0]),
                        "back": _side_payload(sheet.sides[1]),
                    }
                    for sheet in signature.sheets
                ],
            }
        )
    return {
        "schema_version": "imposition_map_v1",
        "layout": "booklet_signature_2up",
        "input_pdf": str(input_pdf),
        "output_pdf": str(output_pdf),
        "page_size": page_size,
        "sheet_size": sheet_size,
        "signature_size": plan.signature_size,
        "duplex_mode": duplex_mode,
        "input_pages": plan.input_pages,
        "padded_pages": plan.padded_pages,
        "blank_count": plan.blank_count,
        "output_sheet_sides": sum(len(sheet.sides) for sig in plan.signatures for sheet in sig.sheets),
        "signatures": signatures,
    }


def _side_payload(side: SheetSide) -> dict[str, object]:
    return {"output_page": side.output_page, "pages": side.pages, "rotate_180": side.rotate_180}


def _close(left: float, right: float, *, tolerance: float) -> bool:
    return abs(left - right) <= tolerance
