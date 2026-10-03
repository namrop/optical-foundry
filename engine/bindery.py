"""E2 — bindery gates Codex 0 taught, as engine checks.

Promoted from the Codex 0 build's book-side scripts (promotion map E2):

* ``folio_run_report`` — ``check_vol3_folio_run.py``. A volume's folios are one run:
  every labelled page arabic, unlabelled pages only in the title block ahead of the run,
  no gaps or repeats, and folio parity equal to physical parity on every page. Parity is
  print-critical and silent: twoside picks a page's margins and running-head side from the
  folio, imposition folds by physical position, and when the two disagree every recto
  typesets as a verso and every outer-margin rail folds into the gutter (Codex 0 build
  45/46 proof sheets, 2026-08-06).
* ``press_sheet_map`` — ``build_press_sheet_map.py``. For a bind PDF (``cli bind-shape``)
  and a signature size: every sheet's four page positions with physical page and printed
  folio (folios from PDF page labels, never arithmetic), its imposed faces, and a
  folio-to-sheet index. Positions come from ``engine.imposition``'s own plan, so the map
  and the imposition cannot disagree. Stock and cut sets are rulings, not derivations:
  pass them in, and a ruled sheet that does not exist is reported.
* ``sewing_stations`` / ``punch_guide_svg`` — ``build_punching_guide.py``. Kettle
  stations at a fixed offset from head and tail, tapes of a given width, and the free
  spine divided into equal gaps; drawn at exact scale (the SVG root is in inches).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.imposition import build_booklet_signature_plan


class BinderyError(ValueError):
    pass


def _labels(pdf: Path) -> list[str]:
    import fitz  # PyMuPDF

    def label(page) -> str:
        try:
            return str(page.get_label() or "").strip()
        except IndexError:  # PyMuPDF: a page ahead of the first label range has none
            return ""

    with fitz.open(str(pdf)) as doc:
        return [label(doc[i]) for i in range(doc.page_count)]


def folio_run_report(pdf: Path) -> dict[str, Any]:
    """Check one volume's folio run; ``problems`` empty means it is well-formed."""
    labels = list(enumerate(_labels(Path(pdf)), start=1))
    numbered = [(p, lab) for p, lab in labels if lab]
    problems: list[str] = []
    if not numbered:
        return {"pdf": str(pdf), "problems": ["the PDF carries no page labels"], "ok": False}
    non_arabic = [(p, lab) for p, lab in numbered if not lab.isdigit()]
    if non_arabic:
        problems.append(f"non-arabic page labels {non_arabic[:6]}: the run is not one arabic sequence")
        return {"pdf": str(pdf), "problems": problems, "ok": False}
    first = numbered[0][0]
    stray = [p for p, lab in labels if not lab and p > first]
    if stray:
        problems.append(f"unlabelled pages after the run opens: {stray[:6]}")
    breaks = [(numbered[i - 1], numbered[i]) for i in range(1, len(numbered))
              if int(numbered[i][1]) != int(numbered[i - 1][1]) + 1 or numbered[i][0] != numbered[i - 1][0] + 1]
    if breaks:
        problems.append(f"the folio run is not continuous: {breaks[:4]}")
    skew = [(p, lab) for p, lab in numbered if p % 2 != int(lab) % 2]
    if skew:
        problems.append(
            f"folio/physical parity disagrees on {len(skew)} page(s), first {skew[0]} (physical page, folio): "
            "every recto from there typesets as a verso and folds its outer margin into the gutter. "
            "One unnumbered leaf ahead of the run realigns the volume.")
    return {"pdf": str(pdf), "numbered": len(numbered), "run": [numbered[0][1], numbered[-1][1]],
            "first_numbered_page": first, "problems": problems, "ok": not problems}


def press_sheet_map(pdf: Path, signature_size: int, *, duplex: str = "short_edge",
                    sheet_sets: dict[str, list[int]] | None = None,
                    ritual_pages: set[int] | None = None) -> dict[str, Any]:
    """Map a bind PDF onto press sheets; ``sheet_sets`` are ruled sets ({"cover": [...]})."""
    labels = _labels(Path(pdf))
    n = len(labels)
    if n % signature_size:
        raise BinderyError(f"{Path(pdf).name} has {n} pages, not a multiple of {signature_size}: "
                           "map the bind PDF (cli bind-shape), not the plain one")
    plan = build_booklet_signature_plan(total_pages=n, signature_size=signature_size, duplex_mode=duplex)
    sheet_sets = sheet_sets or {}
    ritual_pages = ritual_pages or set()
    sheets, index, seen, warnings = [], {}, [], []
    s = 0
    for sig in plan.signatures:
        for sheet in sig.sheets:
            s += 1
            entry: dict[str, Any] = {"sheet": s, "signature": sig.signature_index, "j": sheet.sheet_index,
                                     "imposed_faces": {}, "pages": {}}
            for side in sheet.sides:
                entry["imposed_faces"][side.name] = side.output_page
                for pos, page in zip(("left", "right"), side.pages):
                    if page is None:
                        continue
                    key = f"{side.name}_{pos}"
                    entry["pages"][key] = {"page": page, "folio": labels[page - 1],
                                           "recto": page % 2 == 1, "ritual": page in ritual_pages}
                    seen.append(page)
                    if labels[page - 1]:
                        index.setdefault(labels[page - 1], {"page": page, "sheet": s, "position": key})
            for name, ruled in sheet_sets.items():
                entry[name] = s in ruled
            sheets.append(entry)
    if sorted(seen) != list(range(1, n + 1)):
        raise BinderyError("the sheet map is not a bijection over the bind PDF's pages")
    for name, ruled in sheet_sets.items():
        stray = [x for x in ruled if x > s]
        if stray:
            warnings.append(f"ruled {name} sheet(s) {stray} do not exist ({s} sheets): the ruling is stale")
    return {"pdf": str(pdf), "pages": n, "signature_size": signature_size, "signatures": len(plan.signatures),
            "sheets": s, "duplex": duplex, "sheet_sets": sheet_sets, "sheet_map": sheets,
            "folio_to_sheet": index, "warnings": warnings}


@dataclass(frozen=True)
class Station:
    number: int
    from_head_in: float
    role: str


def sewing_stations(*, fold_height_in: float, kettle_offset_in: float, tapes: int,
                    tape_width_in: float) -> list[Station]:
    """Kettles at the offset; tapes equally spaced so every free run of spine is equal."""
    span = fold_height_in - 2 * kettle_offset_in
    free = span - tapes * tape_width_in
    if span <= 0 or free <= 0 or tapes < 0:
        raise BinderyError("the tapes and kettle offsets do not fit the fold")
    gap = free / (tapes + 1)
    out = [Station(1, kettle_offset_in, "kettle")]
    y = kettle_offset_in
    for t in range(1, tapes + 1):
        y += gap
        out.append(Station(len(out) + 1, y, f"tape {t}, head side"))
        y += tape_width_in
        out.append(Station(len(out) + 1, y, f"tape {t}, tail side"))
    out.append(Station(len(out) + 1, fold_height_in - kettle_offset_in, "kettle"))
    return out


def punch_guide_svg(stations: list[Station], *, fold_height_in: float, strip_width_in: float = 1.5,
                    title: str = "") -> str:
    """An exact-scale punching strip (SVG in inches): fold line, one tick and hole per station."""
    w, h = strip_width_in, fold_height_in
    cx = w / 2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}in" height="{h}in" viewBox="0 0 {w} {h}">',
             f'<rect x="0" y="0" width="{w}" height="{h}" fill="none" stroke="black" stroke-width="0.01"/>',
             f'<line x1="{cx}" y1="0" x2="{cx}" y2="{h}" stroke="#888" stroke-width="0.006" stroke-dasharray="0.05 0.05"/>']
    for st in stations:
        parts.append(f'<line x1="{cx - 0.25:.4f}" y1="{st.from_head_in:.6f}" x2="{cx + 0.25:.4f}" '
                     f'y2="{st.from_head_in:.6f}" stroke="black" stroke-width="0.008"/>')
        parts.append(f'<circle cx="{cx}" cy="{st.from_head_in:.6f}" r="0.02" fill="black"/>')
        parts.append(f'<text x="{cx + 0.3:.4f}" y="{st.from_head_in + 0.03:.6f}" font-size="0.09" '
                     f'font-family="sans-serif">{st.number} · {st.from_head_in:.3f} in</text>')
    if title:
        parts.append(f'<text x="0.05" y="0.12" font-size="0.08" font-family="sans-serif">{title}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
