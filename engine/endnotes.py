"""B4 — a cross-volume endnote sink: one volume prints every volume's notes.

Promoted from the Codex 0 build (``_harvest_volume_endnotes`` and
``_generate_vol3_notes_source``; promotion map B4). Codex 0's reading volumes carry only
the raised note numbers; the apparatus volume prints the notes, grouped by the volume
that carries them and numbered from 1 in each, in reading order.

A volumed manifest asks for it with ``render.endnotes``::

    render:
      endnotes:
        sink: iii                       # the volume id that prints the notes
        title: Notes                    # heading of the generated section
        intro: "The notes that follow ..."   # optional paragraph under it
        group_title: "Notes to {title}" # {title} {id} {number} {roman} of the carrying volume
        before_source_uid: some-uid     # optional; default: the end of the sink volume

``engine.volumes.split_manifest`` then

* numbers every Markdown footnote marker ``[^id]`` in each other volume's sources
  (per source: two sources may both say ``[^1]``), from 1 per volume, in first-marker
  reading order, and records the numbering on that volume (``volume.endnotes``); the
  bundle compiler sets each marker as ``\\OFEndnoteMark{n}`` and drops its definition,
  so the note does not also print at the page foot;
* writes one generated Markdown source holding the notes and adds it to the sink volume.

The sink volume's own footnotes are untouched (they print where they are).

Edition gating (map C1) is not applied here: a marker inside a variant branch that an
edition removes is still harvested. Codex 0 solved this with a second pass over the
edition-resolved intermediates; the engine version will follow C1.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

MARKER_RE = re.compile(r"\[\^([A-Za-z0-9_.-]+)\](?!:)")
DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_.-]+)\]:[ \t]?(.*)$")


class EndnoteError(ValueError):
    pass


def _body(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def _definitions(body: str) -> dict[str, str]:
    """``[^id]: text`` definitions, with indented continuation lines folded in."""
    defs: dict[str, str] = {}
    current: str | None = None
    for line in body.splitlines():
        m = DEF_RE.match(line)
        if m:
            current = m.group(1)
            defs.setdefault(current, m.group(2).strip())
            continue
        if current is not None and line.startswith(("    ", "\t")) and line.strip():
            defs[current] = (defs[current] + " " + line.strip()).strip()
            continue
        current = None
    return defs


def harvest_volume(sources: list[dict[str, Any]], *, base: Path | None = None) -> tuple[dict[str, dict[str, int]], list[tuple[int, str]]]:
    """For one volume: ``({source_uid: {note_id: n}}, [(n, text), ...])``."""
    marks: dict[str, dict[str, int]] = {}
    notes: list[tuple[int, str]] = []
    n = 0
    for src in sources:
        raw = src.get("path")
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute() and base is not None:
            path = base / path
        try:
            body = _body(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        defs = _definitions(body)
        own: dict[str, int] = {}
        for m in MARKER_RE.finditer(body):
            fid = m.group(1)
            if fid in own:
                continue
            n += 1
            own[fid] = n
            notes.append((n, defs.get(fid, "")))
        if own:
            marks[str(src["uid"])] = own
    return marks, notes


def rewrite_markers(body: str, marks: dict[str, int]) -> tuple[str, int]:
    """Set each numbered marker as ``\\OFEndnoteMark{n}`` and drop its definition."""
    if not marks:
        return body, 0
    out: list[str] = []
    skipping = False
    for line in body.splitlines(keepends=True):
        m = DEF_RE.match(line.rstrip("\n"))
        if m and m.group(1) in marks:
            skipping = True
            continue
        if skipping and line.startswith(("    ", "\t")) and line.strip():
            continue
        skipping = False
        out.append(line)
    count = 0

    def mark(m: re.Match) -> str:
        nonlocal count
        n = marks.get(m.group(1))
        if n is None:
            return m.group(0)
        count += 1
        return f"`\\OFEndnoteMark{{{n}}}`{{=latex}}"

    return MARKER_RE.sub(mark, "".join(out)), count


def notes_source(groups: list[tuple[str, list[tuple[int, str]]]], *, title: str, intro: str | None,
                 uid: str) -> str:
    lines = ["---", f"uid: {uid}", "generated_by: engine/endnotes.py (map B4)", "---", "", f"# {title}", ""]
    if intro:
        lines += [intro.strip(), ""]
    for group_title, notes in groups:
        if not notes:
            continue
        lines += [f"## {group_title}", ""]
        for n, text in notes:
            lines += [f"{n}. {text or '(note text not found in the source)'}", ""]
    return "\n".join(lines) + "\n"


def endnotes_config(manifest: dict[str, Any]) -> dict[str, Any] | None:
    cfg = (manifest.get("render") or {}).get("endnotes")
    if not cfg:
        return None
    if not isinstance(cfg, dict) or not cfg.get("sink"):
        raise EndnoteError("render.endnotes needs sink: <volume id>")
    return cfg
