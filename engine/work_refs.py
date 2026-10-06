"""References across the volumes of a work (promotion map step 6).

A volume may cite a page in any volume of the same work, its own included:

    \\OFWorkRef{iii:Contents in Detail}       the folio where Volume iii's outline
                                              entry "Contents in Detail" falls
    \\OFWorkRef[00]{i:Overture}               the same, with a placeholder of its own
    \\OFWorkRef{ii:divider:part-two}          the folio of divider ``part-two``
    \\OFWorkSeat                              this volume's first body folio

The key is ``<volume id>:<what>``. ``<what>`` is an outline title (compared after
normalising case, punctuation and spacing, so ``Wasn't`` and ``Wasn’t`` are one
title) or ``divider:<uid>``. The labels come from the rendered PDFs, never from
arithmetic: a page that owns a folio but prints none still carries its label.

The engine resolves the tokens in the assembled source before pandoc reads it
(engine/manifest_compiler.py), so they reach LaTeX as plain numbers. A key with no
label yet takes the placeholder (default ``000``, the width of a three-digit
folio), so the render that does not know a number yet has the shape of the one
that does. engine/work_render.py renders until every volume was rendered with
the labels the work now has.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DEFAULT_PLACEHOLDER = "000"

# \OFWorkRef[placeholder]{key}; the key may hold any character but braces.
REF_RE = re.compile(r"\\OFWorkRef(?:\[([^\[\]{}]*)\])?\{([^{}]+)\}")
SEAT_RE = re.compile(r"\\OFWorkSeat(?![A-Za-z@])")


class WorkRefError(ValueError):
    pass


def normalize(text: str) -> str:
    """Case, punctuation and spacing folded away: the form two titles are compared in."""
    return " ".join("".join(ch.casefold() if ch.isalnum() else " " for ch in str(text)).split())


def key_of(volume_id: str, what: str) -> str:
    """The canonical table key for ``<volume>:<what>``."""
    what = str(what)
    if what.startswith("divider:"):
        return f"{volume_id}:divider:{what[len('divider:'):]}"
    return f"{volume_id}:{normalize(what)}"


def canonical(raw_key: str) -> str:
    """The table key a source's ``\\OFWorkRef{...}`` names."""
    volume_id, sep, what = raw_key.partition(":")
    if not sep or not volume_id.strip() or not what.strip():
        raise WorkRefError(f"\\OFWorkRef{{{raw_key}}}: the key is <volume id>:<outline title or divider:uid>")
    return key_of(volume_id.strip(), what.strip())


def refs_in(text: str) -> list[str]:
    """The canonical keys a text cites, in order, without repeats."""
    seen: dict[str, None] = {}
    for match in REF_RE.finditer(text):
        seen.setdefault(canonical(match.group(2)), None)
    return list(seen)


def has_tokens(text: str) -> bool:
    return bool(REF_RE.search(text) or SEAT_RE.search(text))


def resolve(text: str, labels: dict[str, str], *, placeholder: str = DEFAULT_PLACEHOLDER,
            seat: int | None = None) -> tuple[str, dict[str, str | None]]:
    """Replace every token; return the text and what each key was resolved to (None: placeholder)."""
    used: dict[str, str | None] = {}

    def ref(match: re.Match[str]) -> str:
        key = canonical(match.group(2))
        value = labels.get(key)
        used[key] = value
        if value is None:
            return match.group(1) if match.group(1) is not None else placeholder
        return str(value)

    out = REF_RE.sub(ref, text)
    if SEAT_RE.search(out):
        if seat is None:
            raise WorkRefError("\\OFWorkSeat is used outside a volume of a work: no seat to give it")
        out = SEAT_RE.sub(str(int(seat)), out)
    return out, used


# --------------------------------------------------------------------------
# Harvest: the labels one rendered volume offers the work
# --------------------------------------------------------------------------

def harvest(volume_id: str, pdf: Path, divider_folios: list[dict[str, Any]] | None = None) -> dict[str, str]:
    """``{key: label}`` for every outline entry and divider of one rendered volume.

    An outline title that occurs twice in the volume is ambiguous; it is left out of
    the table and recorded under ``<volume>:@ambiguous`` so a reference to it fails
    by name rather than citing either page.
    """
    import fitz  # PyMuPDF

    labels: dict[str, str] = {}
    ambiguous: set[str] = set()
    with fitz.open(pdf) as doc:
        page_labels = [doc[i].get_label() or "" for i in range(doc.page_count)]
        for _level, title, page in doc.get_toc(simple=True):
            if not 0 < int(page) <= len(page_labels):
                continue
            key = key_of(volume_id, title)
            label = page_labels[int(page) - 1]
            if key in labels and labels[key] != label:
                ambiguous.add(key)
            labels.setdefault(key, label)
    for key in ambiguous:
        labels.pop(key, None)
    for row in divider_folios or []:
        labels[key_of(volume_id, f"divider:{row['uid']}")] = str(row["folio"])
    if ambiguous:
        labels[f"{volume_id}:@ambiguous"] = "; ".join(sorted(ambiguous))
    return labels


def missing(used: dict[str, str | None], table: dict[str, str], volume_ids: set[str]) -> list[str]:
    """Keys a volume cites that the whole work, fully rendered, does not offer."""
    out = []
    for key in used:
        if key in table:
            continue
        vid = key.split(":", 1)[0]
        if vid not in volume_ids:
            out.append(f"{key} (no volume {vid!r} in this work)")
        elif key in (table.get(f"{vid}:@ambiguous") or "").split("; "):
            out.append(f"{key} (the title occurs more than once in volume {vid})")
        else:
            out.append(f"{key} (volume {vid} has no outline entry or divider by that name)")
    return out
