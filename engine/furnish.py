"""Per-sheet furnish map computation for bound / imposed renders.

Given an imposition mapping (from `engine.imposition._mapping_payload`) plus a
page-to-stock map, this module computes which physical printer sheets need
which stock loaded, and emits a `.furnish.json` structured sidecar plus a
human-readable `.furnish.txt` print run-sheet.

The page-to-stock map is derived by extracting `[[OFDIV:<uid>]]` invisible
markers that the bundle compiler embeds at each divider (see
`manifest_compiler._section_divider_start_lines`), then joining against the
divider inventory in `boundary_assertions["section_dividers"]` to attach each
divider's `stock` field to its landing PDF page. The renderer extracts that map
from the compile-stage PDF, writes it as an out-of-band sidecar, then removes
the hidden text-show operators before the PDF becomes the final reader-facing
artifact. Furnish consumes the preserved map, never the sanitized final PDF.
Non-divider content is implicitly `text` stock.

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
DIVIDER_PAGE_MAP_SCHEMA_VERSION = "divider_page_map_v1"

_MARKER_RE = re.compile(r"\[\[OFDIV:(?P<uid>[A-Za-z0-9_\-]+)\]\]")
_TEXT_SHOW_OPERATORS = {b"Tj", b"TJ", b"'", b'"'}


class DividerMarkerSanitizationError(RuntimeError):
    """Raised when a compile-stage marker cannot be removed from the final PDF."""


@dataclass(frozen=True)
class DividerMarkerSanitizationResult:
    changed: bool
    removed_text_operations: int = 0
    pages_sanitized: list[int] = field(default_factory=list)
    final_pdf_marker_count: int = 0


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


def write_divider_page_map(page_map: dict[str, int], path: Path, *, render_id: str = "") -> None:
    """Persist the compile-stage divider map before final-PDF sanitization."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": DIVIDER_PAGE_MAP_SCHEMA_VERSION,
        "render_id": render_id,
        "source": "compile_stage_pdf_text_layer",
        "divider_page_map": dict(page_map),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def sanitize_divider_markers(
    pdf_path: Path,
    divider_page_map: dict[str, int],
) -> DividerMarkerSanitizationResult:
    """Remove safely isolated invisible OFDIV text-show operators in place.

    The compiler's marker is intentionally emitted inside an ``/OFDIV`` marked-
    content sequence at 1pt under PDF text render mode 3. We preserve all
    graphics-state, marked-content, and positioning operators and remove only
    text-show operators while inside that sequence with mode 3 and a <=1.1pt
    font active, only on pages proven by the pre-sanitization divider map. A
    removable operation must be in a BT/ET object containing no retained
    text-show operation, and the OFDIV bracket itself must begin before BT and
    end after ET. Graphics-state q/Q save and restore applies to the tracked
    render mode and font size. This keeps rendered pixels, text positioning,
    and unrelated hidden text unchanged. The rewritten PDF is validated by
    re-running the marker extractor before it atomically replaces the input.
    """

    if not divider_page_map:
        return DividerMarkerSanitizationResult(changed=False)
    if not pdf_path.exists():
        raise DividerMarkerSanitizationError(f"divider-marker PDF not found: {pdf_path}")

    try:
        from pypdf import PdfWriter  # type: ignore[import-not-found]
        from pypdf.generic import ContentStream  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DividerMarkerSanitizationError(
            "pypdf is required to remove load-bearing OFDIV markers from final PDFs"
        ) from exc

    marker_pages = {int(page) for page in divider_page_map.values() if int(page) > 0}
    if not marker_pages:
        raise DividerMarkerSanitizationError(
            "OFDIV sanitizer received a non-empty divider map without valid marker pages"
        )
    writer = PdfWriter(clone_from=str(pdf_path))
    removed = 0
    pages_sanitized: list[int] = []
    malformed_tag_pages: list[int] = []

    for page_number, page in enumerate(writer.pages, start=1):
        if page_number not in marker_pages or page.get_contents() is None:
            continue
        content = ContentStream(page.get_contents(), writer)
        text_render_mode = 0
        font_size: float | None = None
        graphics_state_trusted = True
        graphics_state_stack: list[tuple[int, float | None, bool]] = []
        marked_content_stack: list[bool] = []
        current_text_object: int | None = None
        next_text_object = 0
        text_structure_trusted = True
        candidate_operations: set[int] = set()
        candidate_text_objects: set[int] = set()
        retained_text_objects: set[int] = set()
        page_failures: list[str] = []

        for operation_index, (operands, operator) in enumerate(content.operations):
            if operator == b"q":
                graphics_state_stack.append(
                    (text_render_mode, font_size, graphics_state_trusted)
                )
            elif operator == b"Q":
                if graphics_state_stack:
                    text_render_mode, font_size, graphics_state_trusted = (
                        graphics_state_stack.pop()
                    )
                else:
                    # A malformed restore makes the inherited state unknowable.
                    # Keep the page permanently conservative so no later text
                    # can become a deletion candidate merely by setting Tr/Tf.
                    text_render_mode = 0
                    font_size = None
                    graphics_state_trusted = False
                    page_failures.append("graphics-state Q underflow")

            if operator in {b"BMC", b"BDC"}:
                is_ofdiv = bool(operands) and str(operands[0]) == "/OFDIV"
                if is_ofdiv and current_text_object is not None:
                    page_failures.append("OFDIV tag begins inside a BT/ET text object")
                marked_content_stack.append(is_ofdiv)
            elif operator == b"EMC":
                if marked_content_stack:
                    is_ofdiv = marked_content_stack.pop()
                    if is_ofdiv and current_text_object is not None:
                        page_failures.append("OFDIV tag ends inside a BT/ET text object")
            elif operator == b"BT":
                if current_text_object is not None:
                    text_structure_trusted = False
                    page_failures.append("nested BT in OFDIV marker page")
                next_text_object += 1
                current_text_object = next_text_object
            elif operator == b"ET":
                if current_text_object is None:
                    text_structure_trusted = False
                    page_failures.append("ET without matching BT in OFDIV marker page")
                current_text_object = None
            elif operator == b"Tr" and operands:
                try:
                    text_render_mode = int(operands[0])
                except (TypeError, ValueError):
                    text_render_mode = 0
            elif operator == b"Tf" and len(operands) >= 2:
                try:
                    font_size = float(operands[1])
                except (TypeError, ValueError):
                    font_size = None

            is_text_show = operator in _TEXT_SHOW_OPERATORS
            is_marker_text = (
                is_text_show
                and any(marked_content_stack)
                and graphics_state_trusted
                and text_render_mode == 3
                and font_size is not None
                and font_size <= 1.1
            )
            if is_marker_text:
                candidate_operations.add(operation_index)
                if current_text_object is None or not text_structure_trusted:
                    page_failures.append(
                        "tagged hidden marker text is not inside a well-formed BT/ET object"
                    )
                else:
                    candidate_text_objects.add(current_text_object)
            elif is_text_show and current_text_object is not None:
                retained_text_objects.add(current_text_object)

        if any(marked_content_stack):
            malformed_tag_pages.append(page_number)
        if current_text_object is not None:
            page_failures.append("unclosed BT/ET text object on OFDIV marker page")

        shared_text_objects = candidate_text_objects & retained_text_objects
        if shared_text_objects:
            page_failures.append(
                "OFDIV marker candidate shares its BT/ET object with retained text-show operations"
            )

        if page_failures:
            raise DividerMarkerSanitizationError(
                f"OFDIV sanitizer refused unsafe marker structure on page {page_number}: "
                + "; ".join(dict.fromkeys(page_failures))
            )

        if candidate_operations:
            removed += len(candidate_operations)
            content.operations = [
                operation
                for operation_index, operation in enumerate(content.operations)
                if operation_index not in candidate_operations
            ]
            page.replace_contents(content)
            pages_sanitized.append(page_number)

    if malformed_tag_pages:
        raise DividerMarkerSanitizationError(
            "OFDIV sanitizer found an unclosed marked-content sequence on page(s): "
            + ", ".join(str(page) for page in malformed_tag_pages)
        )

    missing_pages = marker_pages - set(pages_sanitized)
    if missing_pages:
        raise DividerMarkerSanitizationError(
            "OFDIV sanitizer did not find tagged hidden marker text on expected "
            f"divider page(s): {sorted(missing_pages)}"
        )

    temp_pdf = pdf_path.with_name(f".{pdf_path.name}.ofdiv-sanitize.tmp")
    try:
        with temp_pdf.open("wb") as handle:
            writer.write(handle)
        remaining = extract_divider_page_map(temp_pdf)
        if remaining:
            raise DividerMarkerSanitizationError(
                "OFDIV marker survived final-PDF sanitization: "
                + ", ".join(f"{uid}@{page}" for uid, page in sorted(remaining.items()))
            )
        temp_pdf.replace(pdf_path)
    except OSError as exc:
        raise DividerMarkerSanitizationError(f"could not rewrite sanitized PDF: {exc}") from exc
    finally:
        temp_pdf.unlink(missing_ok=True)

    return DividerMarkerSanitizationResult(
        changed=True,
        removed_text_operations=removed,
        pages_sanitized=pages_sanitized,
        final_pdf_marker_count=len(remaining),
    )


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
