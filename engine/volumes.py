"""B1 and B2: one work in N physical volumes, with a contents of the whole work.

Promotion map B1/B2 (step 3 of ruling 01a0f458-a0ce, as amended by 01a0f8ba-4937).
Codex 0 did this in its own tooling: a shell build seated each volume's first
body folio from the previous volume's PDF, and a 4,500-line projection script
generated the cross-volume contents. Here it is engine behaviour, driven by the
manifest:

* A bundle manifest may carry ``volumes:``, a list of volumes, each starting
  before a named source. ``split_manifest`` cuts it into one ordinary bundle
  manifest per volume (with a ``volume:`` block); nothing else changes.
* ``render_volumes`` renders them in order. Each volume's body starts at the
  folio after the previous volume's last page (**B1, continuous folio
  seating**), on a recto when the document is two-sided (**the physical-sheet
  parity law**: an odd folio must fall on an odd physical page, or a two-sided
  layout puts the outer margin in the gutter).
* When ``render.work_contents`` is on, it then reads every volume's divider
  pages and their PDF page labels and re-renders each volume with a contents of
  the whole work (**B2**). Folio authority is the PDF page label, never the
  printed footer: a page that owns a folio but prints none (a plate, a trailing
  blank) still carries its label. The contents sits in the volume's front
  matter, ahead of the seated body, so it cannot move a body folio; the second
  pass checks that and refuses the result if it did.

The seat itself is template behaviour. A template that already seats
``$body_folio_start$`` (codex0) gets the variable; any other template gets the
engine's generic seat (``\\OFSeatBodyFolio`` in engine/latex/template_contract.tex)
and roman front matter.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
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


def split_manifest(manifest: dict[str, Any], *, base: Path | None = None) -> list[dict[str, Any]]:
    """One ordinary bundle manifest per volume, in order."""
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
    return out


def template_seats_body_folio(profile_id: str) -> bool:
    from engine.profile_resolver import resolve_profile

    template = resolve_profile(profile_id).template_path
    return "$body_folio_start$" in template.read_text(encoding="utf-8", errors="replace")


def _escape(value: Any) -> str:
    from engine.manifest_compiler import _latex_escape_text

    return _latex_escape_text(value)


def work_contents_lines(volume: dict[str, Any]) -> list[str]:
    """The contents of the whole work, as raw LaTeX for the volume's front matter."""
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
        out.append(
            f"\\OFWorkContentsRow{{{_escape(row['title'])}}}{{{_escape(row['volume_label'])}}}"
            f"{{{_escape(row['folio'])}}}{{{here}}}"
        )
    out += ["\\OFWorkContentsEnd", "```", ""]
    return out


def seat_lines(start: int) -> list[str]:
    return ["```{=latex}", f"\\OFSeatBodyFolio{{{int(start)}}}", "```", ""]


# --------------------------------------------------------------------------
# Render side
# --------------------------------------------------------------------------

@dataclass
class VolumeRender:
    id: str
    number: int
    title: str
    render_id: str
    pdf: str
    pages: int
    first_body_folio: int
    last_body_folio: int
    divider_folios: list[dict[str, Any]] = field(default_factory=list)
    evidence_status: str = "ok"


def _labels(pdf: Path) -> list[str]:
    import fitz  # PyMuPDF

    with fitz.open(pdf) as doc:
        return [doc[i].get_label() or "" for i in range(doc.page_count)]


def body_folio_span(pdf: Path) -> tuple[int, int, int]:
    """(pages, first arabic label, last label) — the body is the arabic run that ends the PDF."""
    labels = _labels(pdf)
    if not labels or not labels[-1].isdigit():
        raise VolumeError(f"{pdf.name}: the last page carries the label {labels[-1] if labels else None!r}, not a folio")
    i = len(labels) - 1
    while i > 0 and labels[i - 1].isdigit() and int(labels[i - 1]) == int(labels[i]) - 1:
        i -= 1
    return len(labels), int(labels[i]), int(labels[-1])


def _divider_folios(out_dir: Path, render_id: str, pdf: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    map_path = out_dir / f"{render_id}.divider_pages.json"
    if not map_path.is_file():
        return []
    page_map = json.loads(map_path.read_text(encoding="utf-8")).get("divider_page_map") or {}
    labels = _labels(pdf)
    titles = {d.get("uid"): d.get("title") or d.get("uid") for d in manifest.get("section_dividers") or []}
    rows = []
    for uid, page in sorted(page_map.items(), key=lambda kv: kv[1]):
        label = labels[int(page) - 1] if 0 < int(page) <= len(labels) else ""
        if not label.isdigit():
            raise VolumeError(f"{render_id}: divider {uid} is on page {page}, whose label {label!r} is not a body folio")
        rows.append({"uid": uid, "title": titles.get(uid, uid), "folio": int(label), "page": int(page)})
    return rows


def _render_one(manifest: dict[str, Any], manifest_path: Path | None, out_dir: Path, **render_kwargs: Any):
    from renderers.pandoc_renderer import PandocRenderer

    compiler_cls = _compiler_for(manifest)
    plan = compiler_cls().compile(manifest, manifest_path=manifest_path)
    evidence = PandocRenderer().render(plan, output_dir=str(out_dir), **render_kwargs)
    if evidence.get("status") == "error":
        raise VolumeError(f"{plan.render_id}: render failed: {evidence.get('error')}")
    return plan, evidence


def _compiler_for(manifest: dict[str, Any]):
    from engine.manifest_compiler import CAMStackCompiler, CodexBundleCompiler, CompositeBundleCompiler

    return {"composite_bundle": CompositeBundleCompiler, "cam_stack": CAMStackCompiler,
            "codex_bundle": CodexBundleCompiler}[manifest["kind"]]


def render_volumes(
    manifest: dict[str, Any],
    output_dir: Path,
    *,
    manifest_path: Path | None = None,
    draft: bool = False,
    **render_kwargs: Any,
) -> dict[str, Any]:
    """Render every volume, seat the folios, and (if asked) add the contents of the work."""
    parts = split_manifest(manifest, base=Path(manifest_path).resolve().parent if manifest_path else None)
    render_cfg = manifest.get("render") or {}
    contents_cfg = render_cfg.get("work_contents")
    if isinstance(contents_cfg, bool):
        contents_cfg = {"enabled": contents_cfg}
    want_contents = bool((contents_cfg or {}).get("enabled", False))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def run(pass_name: str, as_draft: bool, contents: dict[str, Any] | None) -> list[VolumeRender]:
        results: list[VolumeRender] = []
        start = 1
        for part in parts:
            part = copy.deepcopy(part)
            part["volume"]["body_folio_start"] = start
            if contents is not None:
                part["volume"]["work_contents"] = contents
            out_dir = output_dir / f"vol-{part['volume']['id']}" / pass_name
            plan, evidence = _render_one(part, manifest_path, out_dir, draft=as_draft, **render_kwargs)
            pdf = Path(evidence["output"]["pdf_path"])
            pages, first, last = body_folio_span(pdf)
            if first != start:
                raise VolumeError(f"{plan.render_id}: body starts at folio {first}, seated at {start}")
            results.append(VolumeRender(
                id=part["volume"]["id"], number=part["volume"]["number"], title=part["volume"]["title"],
                render_id=plan.render_id, pdf=str(pdf), pages=pages, first_body_folio=first,
                last_body_folio=last, divider_folios=_divider_folios(out_dir, plan.render_id, pdf, part),
            ))
            start = last + 1
        return results

    first = run("seat" if want_contents else "final", draft if not want_contents else True, None)
    report: dict[str, Any] = {
        "schema_version": "volume_run_v1",
        "bundle_id": manifest["bundle_id"],
        "volumes": [v.__dict__ for v in first],
        "work_contents": None,
    }
    if want_contents:
        rows = [
            {"volume": v.id, "volume_title": v.title, "volume_label": f"Vol.\u00a0{roman(v.number)}",
             "title": d["title"], "folio": d["folio"], "uid": d["uid"]}
            for v in first for d in v.divider_folios
        ]
        contents = {"title": (contents_cfg or {}).get("title") or "Contents of the Work", "rows": rows}
        final = run("final", draft, contents)
        moved = [
            f"{a.id}: {a.first_body_folio}-{a.last_body_folio} became {b.first_body_folio}-{b.last_body_folio}"
            for a, b in zip(first, final)
            if (a.first_body_folio, a.last_body_folio) != (b.first_body_folio, b.last_body_folio)
        ]
        moved += [
            f"{b.id}: divider {x['uid']} moved from folio {x['folio']} to {y['folio']}"
            for a, b in zip(first, final)
            for x, y in zip(a.divider_folios, b.divider_folios) if x["folio"] != y["folio"]
        ]
        if moved:
            raise VolumeError("the contents of the work moved body folios: " + "; ".join(moved))
        report["volumes"] = [v.__dict__ for v in final]
        report["work_contents"] = {"title": contents["title"], "rows": len(rows),
                                   "verified": "body folios and divider folios identical with and without it"}
    report_path = output_dir / f"{manifest['bundle_id']}.volumes.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
