"""B1 and B2: one work in N physical volumes, with a contents of the whole work.

Promotion map B1/B2 (step 3 of ruling 01a0f458-a0ce, as amended by 01a0f8ba-4937).
Codex 0 did this in its own tooling: a shell build seated each volume's first
body folio from the previous volume's PDF, and a 4,500-line projection script
generated the cross-volume contents. Here it is engine behaviour, driven by the
manifest:

* A bundle manifest may carry ``volumes:``, a list of volumes, each starting
  before a named source. ``split_manifest`` cuts it into one ordinary bundle
  manifest per volume (with a ``volume:`` block); nothing else changes.
* ``engine/work_render.py`` renders them (the work render loop, map step 6).
  Each volume's body starts at the folio after the previous volume's last page
  (**B1, continuous folio seating**), on a recto when the document is two-sided
  (**the physical-sheet parity law**: an odd folio must fall on an odd physical
  page, or a two-sided layout puts the outer margin in the gutter).
* When ``render.work_contents`` is on, every volume carries a contents of the
  whole work (**B2**): each divider's folio is a reference the loop resolves from
  the rendered volumes' PDF page labels. Folio authority is the PDF page label,
  never the printed footer: a page that owns a folio but prints none (a plate, a
  trailing blank) still carries its label.

The seat itself is template behaviour. A template that already seats
``$body_folio_start$`` (codex0) gets the variable; any other template gets the
engine's generic seat (``\\OFSeatBodyFolio`` in engine/latex/template_contract.tex)
and roman front matter.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

ROMAN = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
         (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))

FRONT_MATTER_ROMAN = r"\AtBeginDocument{\pagenumbering{roman}}"


class VolumeError(ValueError):
    pass


def roman(n: int) -> str:
    out = []
    for value, numeral in ROMAN:
        while n >= value:
            out.append(numeral)
            n -= value
    return "".join(out)


# --------------------------------------------------------------------------
# Manifest side
# --------------------------------------------------------------------------

def volume_errors(manifest: dict[str, Any]) -> list[str]:
    """Checks the schema cannot make: the volumes cut the sources in order."""
    volumes = manifest.get("volumes")
    if volumes is None:
        return []
    errors: list[str] = []
    if "volume" in manifest:
        errors.append("a manifest has either volumes (the whole work) or volume (one of them), not both")
    sources = sorted(manifest.get("sources") or [], key=lambda s: s.get("order", 0))
    position = {s.get("uid"): i for i, s in enumerate(sources)}
    last = -1
    ids: set[str] = set()
    for i, vol in enumerate(volumes):
        vid = str(vol.get("id", ""))
        if vid in ids:
            errors.append(f"volumes[{i}].id {vid!r} is repeated")
        ids.add(vid)
        start = vol.get("before_source_uid")
        if i == 0:
            if start not in (None, sources[0].get("uid") if sources else None):
                errors.append("volumes[0] must start at the first source (omit before_source_uid)")
            continue
        if start not in position:
            errors.append(f"volumes[{i}].before_source_uid {start!r} is not a source uid")
            continue
        if position[start] <= last:
            errors.append(f"volumes[{i}] starts before the volume ahead of it ends")
        last = position[start]
    return errors


def split_manifest(
    manifest: dict[str, Any], *, base: Path | None = None, generated_dir: Path | None = None
) -> list[dict[str, Any]]:
    """One ordinary bundle manifest per volume, in order.

    ``generated_dir`` receives sources the engine writes for the work (B4's notes);
    a temporary directory when not given.
    """
    errors = volume_errors(manifest)
    if errors:
        raise VolumeError("; ".join(errors))
    volumes = manifest["volumes"]
    # A5: a volumed work is measured whole, before it is cut, so every volume's
    # colophon prints the same figure.
    from engine.extent import apply_extent

    manifest = copy.deepcopy(manifest)
    extent = apply_extent(manifest, base=base)
    sources = sorted(manifest.get("sources") or [], key=lambda s: s.get("order", 0))
    starts = [0] + [next(i for i, s in enumerate(sources) if s["uid"] == v["before_source_uid"])
                    for v in volumes[1:]]
    ends = starts[1:] + [len(sources)]
    out = []
    for n, (vol, a, b) in enumerate(zip(volumes, starts, ends), start=1):
        part = copy.deepcopy({k: v for k, v in manifest.items() if k != "volumes"})
        chosen = sources[a:b]
        uids = {s["uid"] for s in chosen}
        orders = {s.get("order") for s in chosen}
        part["sources"] = copy.deepcopy(chosen)
        part["section_dividers"] = [
            copy.deepcopy(d) for d in manifest.get("section_dividers") or []
            if d.get("before_source_uid") in uids or d.get("before_source_order") in orders
        ]
        if not part["section_dividers"]:
            part.pop("section_dividers")
        vid = str(vol.get("id") or roman(n).lower())
        part["bundle_id"] = f"{manifest['bundle_id']}-vol-{vid}"
        title = vol.get("title") or f"Volume {roman(n)}"
        pres = dict(part.get("presentation") or {})
        lines = [p for p in (title, vol.get("subtitle")) if p]
        if pres.get("subtitle"):
            lines.insert(0, pres["subtitle"])
        pres["subtitle"] = " · ".join(lines)
        part["presentation"] = pres
        part["volume"] = {"id": vid, "number": n, "count": len(volumes), "title": title}
        if vol.get("subtitle"):
            part["volume"]["subtitle"] = vol["subtitle"]
        if extent:
            part["volume"]["extent"] = dict(extent)
        out.append(part)
    _sink_endnotes(manifest, out, base=base, generated_dir=generated_dir)
    return out


def _sink_endnotes(manifest: dict[str, Any], parts: list[dict[str, Any]], *, base: Path | None,
                   generated_dir: Path | None) -> None:
    """B4: number the other volumes' notes and print them all in the sink volume."""
    from engine.endnotes import endnotes_config, harvest_volume, notes_source

    cfg = endnotes_config(manifest)
    if cfg is None:
        return
    sink_id = str(cfg["sink"])
    sink = next((p for p in parts if p["volume"]["id"] == sink_id), None)
    if sink is None:
        raise VolumeError(f"render.endnotes.sink {sink_id!r} is not a volume id")
    groups = []
    for part in parts:
        if part is sink:
            continue
        marks, notes = harvest_volume(part["sources"], base=base)
        if marks:
            part["volume"]["endnotes"] = {"sink": sink_id, "marks": marks, "count": len(notes)}
        vol = part["volume"]
        fields = {"title": vol["title"], "id": vol["id"], "number": vol["number"], "roman": roman(vol["number"])}
        groups.append((str(cfg.get("group_title", "Notes to {title}")).format(**fields), notes))
    if not any(notes for _, notes in groups):
        return
    if generated_dir is None:
        import tempfile

        generated_dir = Path(tempfile.mkdtemp(prefix="of_volumes_"))
    generated_dir = Path(generated_dir)
    generated_dir.mkdir(parents=True, exist_ok=True)
    uid = f"{manifest['bundle_id']}-endnotes"
    path = generated_dir / f"{uid}.md"
    path.write_text(notes_source(groups, title=str(cfg.get("title", "Notes")), intro=cfg.get("intro"), uid=uid),
                    encoding="utf-8")
    sources = sink["sources"]
    entry = {"uid": uid, "path": str(path), "role": "appendix", "title": str(cfg.get("title", "Notes")),
             "include_frontmatter": "none", "suppress_frontmatter": True}
    before = cfg.get("before_source_uid")
    if before:
        at = next((i for i, s in enumerate(sources) if s["uid"] == before), None)
        if at is None:
            raise VolumeError(f"render.endnotes.before_source_uid {before!r} is not a source of volume {sink_id}")
    else:
        at = len(sources)
    sources.insert(at, entry)
    # Orders stay increasing: the notes take the slot, the rest shift by one.
    for i, s in enumerate(sources):
        s["order"] = i + 1
    sink["volume"]["endnotes"] = {"sink": sink_id, "notes_source_uid": uid,
                                  "count": sum(len(n) for _, n in groups)}


def template_seats_body_folio(profile_id: str) -> bool:
    from engine.profile_resolver import resolve_profile

    template = resolve_profile(profile_id).template_path
    return "$body_folio_start$" in template.read_text(encoding="utf-8", errors="replace")


def _escape(value: Any) -> str:
    from engine.manifest_compiler import _latex_escape_text

    return _latex_escape_text(value)


def work_contents_lines(volume: dict[str, Any]) -> list[str]:
    """The contents of the whole work, as raw LaTeX for the volume's front matter.

    A row's folio is ``folio`` when given, else a reference (``ref``) the compiler
    resolves from the work's labels (engine/work_refs.py).
    """
    contents = volume.get("work_contents")
    if not contents:
        return []
    rows = contents.get("rows") or []
    out = ["```{=latex}", f"\\OFWorkContentsBegin{{{_escape(contents.get('title') or 'Contents of the Work')}}}"]
    current = None
    for row in rows:
        if row["volume"] != current:
            current = row["volume"]
            out.append(f"\\OFWorkContentsVolume{{{_escape(row['volume_title'])}}}")
        here = 1 if row["volume"] == volume.get("id") else 0
        folio = _escape(row["folio"]) if row.get("folio") is not None else f"\\OFWorkRef{{{row['ref']}}}"
        out.append(
            f"\\OFWorkContentsRow{{{_escape(row['title'])}}}{{{_escape(row['volume_label'])}}}"
            f"{{{folio}}}{{{here}}}"
        )
    out += ["\\OFWorkContentsEnd", "```", ""]
    return out


def seat_lines(start: int) -> list[str]:
    return ["```{=latex}", f"\\OFSeatBodyFolio{{{int(start)}}}", "```", ""]
