"""Gates for multi-pass builds: prove a render did not move.

A pass that consumes a prior render's page labels is only as good as the proof
that the render it read and the render that ships have the same shape. Promoted
from the Codex 0 build (PASS C3, D1c, G3; promotion map B3, 2026-09-28) as the
assertion half of pass orchestration; the pass order itself stays with the work
until a second multi-pass consumer exists.

``compare_renders`` compares two PDFs of the same bundle — typically a draft
render (``cli manifest --draft``: image boxes, no image data) and the full
render — on everything a later pass can harvest: page count, the label of every
page, and the outline (level, title, page, destination height). Text is not
compared: a draft prints each image's file name inside its box.
"""
from __future__ import annotations

from pathlib import Path


def _outline(doc) -> list[tuple]:
    rows = []
    for entry in doc.get_toc(simple=False):
        level, title, page = entry[0], entry[1], entry[2]
        dest = entry[3] if len(entry) > 3 and isinstance(entry[3], dict) else {}
        to = dest.get("to")
        rows.append((level, title, page, round(to.y, 1) if to is not None else None))
    return rows


def compare_renders(reference: Path, candidate: Path) -> list[str]:
    """Differences between two renders of one bundle; empty means same shape."""
    import fitz  # PyMuPDF; imported lazily so the engine imports without it

    a, b = fitz.open(str(reference)), fitz.open(str(candidate))
    try:
        if a.page_count != b.page_count:
            return [f"page count {a.page_count} != {b.page_count}"]
        diffs = []
        for i in range(a.page_count):
            la, lb = a[i].get_label(), b[i].get_label()
            if la != lb:
                diffs.append(f"page {i + 1}: label {la!r} != {lb!r}")
                if len(diffs) >= 10:
                    break
        oa, ob = _outline(a), _outline(b)
        if oa != ob:
            if len(oa) != len(ob):
                diffs.append(f"outline entries {len(oa)} != {len(ob)}")
            else:
                first = next(i for i in range(len(oa)) if oa[i] != ob[i])
                diffs.append(f"outline entry {first + 1}: {oa[first]} != {ob[first]}")
        return diffs
    finally:
        a.close()
        b.close()
