"""D3 — floating plates and their containment check; D5 — page-number-keyed page marks.

Promoted from the Codex 0 build (promotion map D3: b7baf9b, c050cb3, cea2861 and the
build gate ``tooling/check_plate_containment.py``; D5: c050cb3). A full-page plate is
anchored in the text where it belongs (``\\OFFloatingPlate{asset}``) and the engine seats
it during pagination on the first legal recto (engine/latex/of_plate_float.lua). Because
any upstream edit can push a correctly seated plate onto the wrong spread, containment
is re-proved on every render, not trusted (Codex 0 build 64).

A manifest asks for it with::

    render:
      plates:
        floating: true      # load the injector and the plate page style (LuaLaTeX)
        gate: true          # a containment violation fails the render (default true)

The check reads the page ledger the render carries out in the PDF's Info dictionary
(engine/latex/of_pages.lua; the renderer saves it as ``<render_id>.pages.json`` and
strips it from the published PDF): every shipped page with the chapter it starts and
ends in, whether a chapter opens on it, and its marks. It applies the law to what
shipped:

* a plate's facing page (a recto faces the verso before it, a verso the recto after it)
  must lie wholly inside the plate's owner chapter, or not exist;
* a plate may not face its chapter's opening page unless it allows it (``|allow-opener``);
* every declared plate must have been placed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ENGINE_LATEX = Path(__file__).resolve().parent / "latex"


class PlateError(ValueError):
    pass


def plates_config(render_cfg: dict[str, Any] | None) -> dict[str, Any] | None:
    cfg = (render_cfg or {}).get("plates")
    if not cfg:
        return None
    if not isinstance(cfg, dict):
        raise PlateError("render.plates must be a mapping, e.g. {floating: true}")
    if not cfg.get("floating", True):
        return None
    return {"floating": True, "gate": bool(cfg.get("gate", True))}


def ledger_path(output_dir: Path, render_id: str) -> Path:
    return Path(output_dir) / f"{render_id}.pages.json"


LEDGER_KEY = "OFPageLedger"


def preamble_lines() -> list[str]:
    return [
        "\\usepackage{etoolbox}",
        "\\usepackage{graphicx}",
        f"\\input{{{(ENGINE_LATEX / 'of_plates.tex').as_posix()}}}",
    ]


def _info_xref(doc) -> int | None:
    kind, value = doc.xref_get_key(-1, "Info")
    if kind != "xref":
        return None
    return int(value.split()[0])


def extract_ledger(pdf: Path, *, strip: bool = True) -> dict[str, Any] | None:
    """The page ledger the render carried out in the PDF's Info dictionary.

    With ``strip`` the key is removed and the PDF rewritten, so the published PDF
    does not carry it (it names asset paths). None when the PDF has no ledger.
    """
    import fitz  # PyMuPDF

    pdf = Path(pdf)
    doc = fitz.open(str(pdf))
    try:
        xref = _info_xref(doc)
        if xref is None:
            return None
        kind, value = doc.xref_get_key(xref, LEDGER_KEY)
        if kind != "string" or not value:
            return None
        try:
            ledger = json.loads(bytes.fromhex(value).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PlateError(f"page ledger in {pdf.name} is unreadable: {exc}") from None
        if strip:
            doc.xref_set_key(xref, LEDGER_KEY, "null")
            tmp = pdf.with_name(pdf.name + ".ledger-stripped")
            doc.save(str(tmp))
            doc.close()
            tmp.replace(pdf)
        return ledger
    finally:
        if not doc.is_closed:
            doc.close()


def check_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    """Apply the containment law to a page ledger; violations empty means it holds."""
    pages: list[dict[str, Any]] = ledger.get("pages") or []
    by_page: dict[int, int] = {}
    for i, entry in enumerate(pages):
        if "plate" in (entry.get("marks") or []):
            by_page[int(entry["page"])] = i
    findings: list[dict[str, Any]] = []
    for plate in ledger.get("plates") or []:
        i = by_page.get(int(plate["page"]))
        if i is None:
            findings.append({**plate, "contained": False, "reason": "plate page not in the ledger"})
            continue
        n = i + 1                              # physical page, 1-based; odd = recto
        facing = n - 1 if n % 2 == 1 else n + 1
        owner = plate.get("owner") or ""
        row: dict[str, Any] = {"asset": plate.get("asset"), "owner": owner, "page": n,
                               "folio": pages[i].get("label"), "side": "recto" if n % 2 else "verso",
                               "facing_page": facing}
        if not 1 <= facing <= len(pages):
            row.update(contained=True, facing_chapter=None, reason=None)
            findings.append(row)
            continue
        f = pages[facing - 1]
        row["facing_chapter"] = f.get("start") if f.get("start") == f.get("end") else f"{f.get('start')} -> {f.get('end')}"
        whole = (not owner) or (f.get("start") == owner and f.get("end") == owner)
        isolates = bool(f.get("opener")) and not plate.get("allow_opener")
        reason = None
        if not whole:
            reason = f"shares its spread with {row['facing_chapter']!r}"
        elif isolates:
            reason = "faces its chapter's opening page"
        row.update(contained=reason is None, reason=reason, isolates_opening=isolates)
        findings.append(row)
    unplaced = list(ledger.get("unplaced") or [])
    violations = [f for f in findings if not f["contained"]]
    return {"plates": findings, "violations": violations, "unplaced": unplaced,
            "ok": not violations and not unplaced}


def check_render(output_dir: Path, render_id: str) -> dict[str, Any] | None:
    path = ledger_path(output_dir, render_id)
    if not path.is_file():
        return None
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"page ledger is not JSON: {exc}", "plates": [], "violations": [], "unplaced": []}
    report = check_ledger(ledger)
    report["ledger"] = str(path)
    return report
