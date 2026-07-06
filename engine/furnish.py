"""Per-sheet furnish map computation for bound / imposed renders.

Given an imposition mapping (from `engine.imposition._mapping_payload`) plus a
page-to-stock map, this module computes which physical printer sheets need
which stock loaded, and emits a `.furnish.json` structured sidecar plus a
human-readable `.furnish.txt` print run-sheet.

The page-to-stock map is derived by extracting `[[OFDIV:<uid>]]` invisible
markers that the bundle compiler embeds at each divider (see
`manifest_compiler._section_divider_start_lines`), then joining against the
divider inventory in `boundary_assertions["section_dividers"]` to attach each
divider's `stock` field to its landing PDF page. Non-divider content is
implicitly `text` stock.

The furnish map does not decide what to *do* about mixed-stock sheets — it
reports them. Callers (or a downstream policy layer) decide whether to
hard-error, auto-pad cardstock onto its own sheets (wasting the verso), or
proceed with a warning.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


TEXT_STOCK = "text"
FURNISH_SCHEMA_VERSION = "furnish_map_v1"

_MARKER_RE = re.compile(r"\[\[OFDIV:(?P<uid>[A-Za-z0-9_\-]+)\]\]")


@dataclass(frozen=True)
class SheetSideFurnish:
    sheet_index: int
    side: str  # "front" | "back"
    output_page: int
    pages: list[int | None]
    page_stocks: list[str]  # per pages entry, aligned with `pages`
    stock: str  # resolved side stock
    mixed_stocks_present: bool


@dataclass(frozen=True)
class FurnishMap:
    schema_version: str = FURNISH_SCHEMA_VERSION
    input_pdf: str = ""
    imposition_mapping: str = ""
    total_signatures: int = 0
    total_sheets: int = 0
    sheet_sides: list[SheetSideFurnish] = field(default_factory=list)
    stock_summary: dict[str, int] = field(default_factory=dict)  # stock → sheet-side count
    warnings: list[str] = field(default_factory=list)
    divider_page_map: dict[str, int] = field(default_factory=dict)  # uid → 1-based PDF page

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_pdf": self.input_pdf,
            "imposition_mapping": self.imposition_mapping,
            "total_signatures": self.total_signatures,
            "total_sheets": self.total_sheets,
            "stock_summary": dict(self.stock_summary),
            "divider_page_map": dict(self.divider_page_map),
            "sheet_sides": [
                {
                    "sheet_index": s.sheet_index,
                    "side": s.side,
                    "output_page": s.output_page,
                    "pages": list(s.pages),
                    "page_stocks": list(s.page_stocks),
                    "stock": s.stock,
                    "mixed_stocks_present": s.mixed_stocks_present,
                }
                for s in self.sheet_sides
            ],
            "warnings": list(self.warnings),
        }


def extract_divider_page_map(pdf_path: Path) -> dict[str, int]:
    """Return uid → 1-based PDF page for every `[[OFDIV:<uid>]]` marker in the PDF.

    Uses pdftotext with page-break preservation. If pdftotext is not on PATH or
    the PDF has no markers, returns an empty dict.
    """
    if not pdf_path.exists():
        return {}
    if shutil.which("pdftotext") is None:
        return {}
    try:
        # Emit page breaks (\f, form feed) between pages so we can count.
        proc = subprocess.run(
            ["pdftotext", "-raw", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {}
    text = proc.stdout
    page_map: dict[str, int] = {}
    for page_index, page_text in enumerate(text.split("\f"), start=1):
        for match in _MARKER_RE.finditer(page_text):
            uid = match.group("uid")
            # Take first occurrence per uid (dividers should only occur once).
            page_map.setdefault(uid, page_index)
    return page_map


def build_page_to_stock(
    total_pdf_pages: int,
    divider_page_map: dict[str, int],
    divider_inventory: Iterable[dict[str, Any]],
) -> dict[int, str]:
    """Return PDF-page → stock. Unspecified pages default to `text` stock.

    A divider occupies exactly one page (the recto it opens on); subsequent
    content pages until the next divider are implicitly text stock. If a
    divider has `blank_after: true`, the following blank verso is also
    considered part of the divider's stock envelope (the physical divider card
    typically has printing only on the recto but is one physical sheet-side of
    heavier stock in either case).
    """
    inv_by_uid = {str(d.get("uid", "")): d for d in divider_inventory}
    result: dict[int, str] = {}
    for uid, page in divider_page_map.items():
        divider = inv_by_uid.get(uid)
        if not divider:
            continue
        stock = str(divider.get("stock", "") or TEXT_STOCK).strip().lower() or TEXT_STOCK
        result[page] = stock
        if divider.get("blank_after") and page + 1 <= total_pdf_pages:
            result[page + 1] = stock
    return result


def compute_furnish(
    imposition_mapping: dict[str, Any],
    page_to_stock: dict[int, str],
    *,
    input_pdf: Path | None = None,
    imposition_mapping_path: Path | None = None,
    divider_page_map: dict[str, int] | None = None,
) -> FurnishMap:
    """Compute per-sheet-side furnish from an imposition_map_v1 payload."""
    sheet_sides: list[SheetSideFurnish] = []
    stock_summary: dict[str, int] = {}
    warnings: list[str] = []

    signatures = imposition_mapping.get("signatures", []) if isinstance(imposition_mapping, dict) else []
    total_signatures = len(signatures)
    total_sheets = sum(len(sig.get("sheets", [])) for sig in signatures if isinstance(sig, dict))

    for sig in signatures:
        if not isinstance(sig, dict):
            continue
        for sheet in sig.get("sheets", []) or []:
            if not isinstance(sheet, dict):
                continue
            sheet_index = int(sheet.get("sheet_index", 0))
            for side_name in ("front", "back"):
                side = sheet.get(side_name)
                if not isinstance(side, dict):
                    continue
                pages = list(side.get("pages") or [])
                output_page = int(side.get("output_page", 0))
                page_stocks = [
                    (page_to_stock.get(int(p)) if isinstance(p, int) else TEXT_STOCK) or TEXT_STOCK
                    for p in pages
                ]
                non_text = {s for s in page_stocks if s and s != TEXT_STOCK}
                mixed = bool(non_text) and (len(non_text) > 1 or TEXT_STOCK in page_stocks)
                stock = sorted(non_text)[0] if non_text else TEXT_STOCK
                stock_summary[stock] = stock_summary.get(stock, 0) + 1
                if mixed:
                    warnings.append(
                        f"sheet {sheet_index} {side_name}: mixed stock — pages {pages} → {page_stocks}. "
                        "Consider padding cardstock content onto its own sheet or accepting a mixed sheet."
                    )
                sheet_sides.append(SheetSideFurnish(
                    sheet_index=sheet_index,
                    side=side_name,
                    output_page=output_page,
                    pages=pages,
                    page_stocks=page_stocks,
                    stock=stock,
                    mixed_stocks_present=mixed,
                ))

    return FurnishMap(
        input_pdf=str(input_pdf) if input_pdf is not None else "",
        imposition_mapping=str(imposition_mapping_path) if imposition_mapping_path is not None else "",
        total_signatures=total_signatures,
        total_sheets=total_sheets,
        sheet_sides=sheet_sides,
        stock_summary=stock_summary,
        warnings=warnings,
        divider_page_map=dict(divider_page_map or {}),
    )


def write_furnish_json(furnish: FurnishMap, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(furnish.to_dict(), indent=2) + "\n")


def write_furnish_text(furnish: FurnishMap, path: Path) -> None:
    """Human-readable print run-sheet."""
    lines: list[str] = []
    lines.append("Furnish plan — Optical Foundry")
    lines.append(f"Input PDF: {furnish.input_pdf}")
    lines.append(f"Imposition mapping: {furnish.imposition_mapping}")
    lines.append(f"Signatures: {furnish.total_signatures}   Sheets: {furnish.total_sheets}")
    lines.append("")
    lines.append("Stock summary (sheet-sides per stock):")
    for stock, count in sorted(furnish.stock_summary.items()):
        lines.append(f"  {stock:12} {count}")
    lines.append("")
    lines.append("Non-text-stock sheet-sides (load alternate stock before printing):")
    alt = [s for s in furnish.sheet_sides if s.stock != TEXT_STOCK]
    if not alt:
        lines.append("  (none — every sheet-side is on text stock)")
    else:
        for s in alt:
            marker = " *MIXED*" if s.mixed_stocks_present else ""
            lines.append(f"  sheet {s.sheet_index:3d} {s.side:5} (output page {s.output_page:3d}): "
                         f"stock={s.stock}, pages={s.pages}{marker}")
    lines.append("")
    if furnish.warnings:
        lines.append("Warnings:")
        for w in furnish.warnings:
            lines.append(f"  - {w}")
        lines.append("")
    if furnish.divider_page_map:
        lines.append("Divider page landings (for reconciliation with imposition slots):")
        for uid, page in sorted(furnish.divider_page_map.items(), key=lambda kv: kv[1]):
            lines.append(f"  page {page:3d}  {uid}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
