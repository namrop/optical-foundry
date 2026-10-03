"""E3 — print sheets with non-uniform placements (labels, spine labels, cards).

Promotion map E3: ``sticker_sheet_manifest_v1`` is a uniform grid (one ``grid``, one
``cell_size``), and Codex 0's label contract needs a cover label plus three spine labels
of different sizes, one title rotated. Codex 0 worked around it with a book-side script
(``tooling/build_cover_label_print_sheet.py``). This is the general capability: a
manifest places each item at an exact physical position and size on a sheet.

Manifest (``kind: print_sheet``, ``schema_version: print_sheet_v1``)::

    kind: print_sheet
    schema_version: print_sheet_v1
    sheet_id: codex0-labels
    page: {size: letter}                 # letter | a4 | half_letter, or {width, height}
    min_dpi: 300                         # each image at its placed size (default 300)
    cut_marks: {length: 4mm, offset: 2mm, weight: 0.25pt}   # or false
    items:
      - id: cover
        image: labels/cover.png          # relative to the manifest
        x: 0.5in                         # top-left of the placed box, from the page's top-left
        y: 1.0in
        width: 3.75in                    # the box as it sits on the page (after rotation)
        height: 7.0in
        rotate: 0                        # 0 | 90 | 180 | 270, clockwise
        copies: [{x: 4.5in, y: 1.0in}]   # optional: the same item again elsewhere

Checks: every box inside the page (and its cut marks inside the page), no two boxes
overlapping, the image's aspect matching its box within 1% (a label is printed at its
size, never stretched or letterboxed), and at least ``min_dpi`` at the placed size.
Placement is exact: no scaling to fit, no centring. Evidence records every placed box.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import yaml

KIND, SCHEMA = "print_sheet", "print_sheet_v1"
PT = {"in": 72.0, "mm": 72.0 / 25.4, "cm": 720.0 / 25.4, "pt": 1.0}
PAGES = {"letter": (612.0, 792.0), "a4": (595.276, 841.89), "half_letter": (396.0, 612.0)}
_DIM_RE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*(in|mm|cm|pt)\s*$")


class PrintSheetError(ValueError):
    pass


def to_pt(value: Any, what: str) -> float:
    m = _DIM_RE.match(str(value))
    if not m:
        raise PrintSheetError(f"{what}: {value!r} is not a length like 3.75in or 95mm")
    return float(m.group(1)) * PT[m.group(2)]


@dataclass(frozen=True)
class Placed:
    id: str
    image: Path
    x: float
    y: float
    w: float
    h: float
    rotate: int


def plan(manifest: dict[str, Any], *, base: Path) -> tuple[tuple[float, float], list[Placed], dict[str, Any]]:
    if manifest.get("kind") != KIND or manifest.get("schema_version") != SCHEMA:
        raise PrintSheetError(f"expected kind: {KIND}, schema_version: {SCHEMA}")
    page = manifest.get("page") or {"size": "letter"}
    if "size" in page:
        if page["size"] not in PAGES:
            raise PrintSheetError(f"page.size must be one of {sorted(PAGES)}")
        pw, ph = PAGES[page["size"]]
    else:
        pw, ph = to_pt(page.get("width"), "page.width"), to_pt(page.get("height"), "page.height")
    marks = manifest.get("cut_marks", {})
    marks = {} if marks is False else {"length": to_pt((marks or {}).get("length", "4mm"), "cut_marks.length"),
                                       "offset": to_pt((marks or {}).get("offset", "2mm"), "cut_marks.offset"),
                                       "weight": to_pt((marks or {}).get("weight", "0.25pt"), "cut_marks.weight")}
    reach = (marks["length"] + marks["offset"]) if marks else 0.0
    placed: list[Placed] = []
    errors: list[str] = []
    for i, item in enumerate(manifest.get("items") or []):
        iid = str(item.get("id") or f"item{i + 1}")
        image = Path(item["image"]) if "image" in item else None
        if image is None:
            errors.append(f"{iid}: no image")
            continue
        if not image.is_absolute():
            image = base / image
        rot = int(item.get("rotate", 0))
        if rot not in (0, 90, 180, 270):
            errors.append(f"{iid}: rotate must be 0, 90, 180 or 270")
            continue
        w, h = to_pt(item.get("width"), f"{iid}.width"), to_pt(item.get("height"), f"{iid}.height")
        spots = [item] + list(item.get("copies") or [])
        for n, spot in enumerate(spots):
            pid = iid if n == 0 else f"{iid}#{n + 1}"
            placed.append(Placed(pid, image, to_pt(spot.get("x"), f"{pid}.x"), to_pt(spot.get("y"), f"{pid}.y"),
                                 w, h, rot))
    if not placed and not errors:
        errors.append("items: nothing to place")
    for p in placed:
        if p.x - reach < -0.01 or p.y - reach < -0.01 or p.x + p.w + reach > pw + 0.01 or p.y + p.h + reach > ph + 0.01:
            errors.append(f"{p.id}: box (with its cut marks) runs off the page")
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h:
                errors.append(f"{a.id} and {b.id} overlap")
    min_dpi = float(manifest.get("min_dpi", 300))
    records = []
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        Image = None
    for p in placed:
        rec: dict[str, Any] = {"id": p.id, "image": str(p.image), "rotate": p.rotate,
                               "box_in": [round(v / 72, 4) for v in (p.x, p.y, p.w, p.h)]}
        if not p.image.is_file():
            errors.append(f"{p.id}: image not found: {p.image}")
            records.append(rec)
            continue
        if Image is not None:
            with Image.open(p.image) as im:
                iw, ih = im.size
            # the image's own width runs along the box's height when turned a quarter
            bw, bh = (p.h, p.w) if p.rotate in (90, 270) else (p.w, p.h)
            if abs((iw / ih) / (bw / bh) - 1) > 0.01:
                errors.append(f"{p.id}: image aspect {iw / ih:.4f} does not match its box {bw / bh:.4f} "
                              "(placement is exact: no stretching, no letterbox)")
            dpi = min(iw / (bw / 72), ih / (bh / 72))
            rec["dpi"] = round(dpi, 1)
            if dpi + 0.5 < min_dpi:
                errors.append(f"{p.id}: {dpi:.0f} dpi at its placed size, below {min_dpi:.0f}")
        records.append(rec)
    if errors:
        raise PrintSheetError("; ".join(errors))
    return (pw, ph), placed, {"page_pt": [pw, ph], "cut_marks": bool(marks), "items": records, "_marks": marks}


def render(manifest_path: Path, output: Path | None = None) -> dict[str, Any]:
    import fitz  # PyMuPDF

    manifest_path = Path(manifest_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    (pw, ph), placed, record = plan(manifest, base=manifest_path.resolve().parent)
    marks = record.pop("_marks")
    sheet_id = str(manifest.get("sheet_id") or manifest_path.stem)
    output = Path(output) if output else manifest_path.resolve().parent / f"{sheet_id}.pdf"
    if output.suffix.lower() != ".pdf":
        output = output / f"{sheet_id}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=pw, height=ph)
    for p in placed:
        # PyMuPDF rotates counter-clockwise; the manifest says clockwise.
        page.insert_image(fitz.Rect(p.x, p.y, p.x + p.w, p.y + p.h), filename=str(p.image),
                          rotate=(360 - p.rotate) % 360, keep_proportion=False)
        if marks:
            L, o, wt = marks["length"], marks["offset"], marks["weight"]
            for cx in (p.x, p.x + p.w):
                for cy, sgn in ((p.y, -1), (p.y + p.h, 1)):
                    page.draw_line((cx, cy + sgn * o), (cx, cy + sgn * (o + L)), width=wt)
            for cy in (p.y, p.y + p.h):
                for cx, sgn in ((p.x, -1), (p.x + p.w, 1)):
                    page.draw_line((cx + sgn * o, cy), (cx + sgn * (o + L), cy), width=wt)
    doc.save(str(output))
    doc.close()
    evidence = {"schema_version": "print_sheet_evidence_v1", "sheet_id": sheet_id, "status": "ok",
                "manifest": str(manifest_path), "output": str(output), **record}
    output.with_suffix(".evidence.json").write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8")
    return evidence
