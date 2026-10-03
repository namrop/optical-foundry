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


def passes_config(render_cfg: dict[str, Any]) -> dict[str, Any] | None:
    """B3: ``render.passes`` — opt in to planned passes (optional by default, as ruled).

    ``{final_parallel: N, prove_final: true}``: every measuring pass renders in draft
    (image boxes, no image data), each pass that reads a prior pass's labels proves the
    prior pass did not move, the final volumes render once, full, ``N`` at a time (their
    folios are known from the drafts), and each final is proved against its last draft
    (page count, every label, outline). A failed proof stops the build: past a folio move
    a fixed point is not guaranteed to exist, so there is no retry.
    """
    cfg = render_cfg.get("passes")
    if not cfg:
        return None
    if not isinstance(cfg, dict):
        raise VolumeError("render.passes must be a mapping, e.g. {final_parallel: 3}")
    n = int(cfg.get("final_parallel", 1))
    if n < 1:
        raise VolumeError("render.passes.final_parallel must be at least 1")
    return {"final_parallel": n, "prove_final": bool(cfg.get("prove_final", True))}


def _planned(parts, passes, one, run, want_contents, contents_cfg, manifest, output_dir) -> dict[str, Any]:
    """B3: draft measuring passes, fixed-point gates, one parallel final wave, final proofs."""
    from concurrent.futures import ThreadPoolExecutor

    from engine.pass_gates import compare_renders

    log: list[dict[str, Any]] = []
    drafts = run("seat", True, None)
    log.append({"pass": "seat", "draft": True, "volumes": len(drafts)})
    contents = None
    if want_contents:
        rows = [
            {"volume": v.id, "volume_title": v.title, "volume_label": f"Vol.\u00a0{roman(v.number)}",
             "title": d["title"], "folio": d["folio"], "uid": d["uid"]}
            for v in drafts for d in v.divider_folios
        ]
        contents = {"title": (contents_cfg or {}).get("title") or "Contents of the Work", "rows": rows}
        second = run("contents", True, contents)
        # Fixed-point gate: the pass that consumed the seat pass's labels must not move them.
        moved = [
            f"{a.id}: {a.first_body_folio}-{a.last_body_folio} became {b.first_body_folio}-{b.last_body_folio}"
            for a, b in zip(drafts, second)
            if (a.first_body_folio, a.last_body_folio) != (b.first_body_folio, b.last_body_folio)
        ] + [
            f"{b.id}: divider {x['uid']} moved from folio {x['folio']} to {y['folio']}"
            for a, b in zip(drafts, second)
            for x, y in zip(a.divider_folios, b.divider_folios) if x["folio"] != y["folio"]
        ]
        log.append({"pass": "contents", "draft": True, "fixed_point": not moved})
        if moved:
            raise VolumeError("fixed point not reached (the contents pass moved folios; no retry): " + "; ".join(moved))
        drafts = second
    starts = [d.first_body_folio for d in drafts]
    with ThreadPoolExecutor(max_workers=passes["final_parallel"]) as pool:
        finals = list(pool.map(lambda args: one(args[0], args[1], "final", False, contents), zip(parts, starts)))
    log.append({"pass": "final", "draft": False, "parallel": passes["final_parallel"]})
    proofs = []
    if passes["prove_final"]:
        for d, f in zip(drafts, finals):
            diffs = compare_renders(Path(d.pdf), Path(f.pdf))
            proofs.append({"volume": f.id, "same_shape": not diffs, "differences": diffs[:10]})
        log.append({"pass": "prove", "ok": all(p["same_shape"] for p in proofs)})
        bad = [p for p in proofs if not p["same_shape"]]
        if bad:
            raise VolumeError("a final volume does not have its draft's shape: "
                              + "; ".join(f"{p['volume']}: {p['differences'][0]}" for p in bad))
    report: dict[str, Any] = {
        "schema_version": "volume_run_v1",
        "bundle_id": manifest["bundle_id"],
        "volumes": [v.__dict__ for v in finals],
        "work_contents": ({"title": contents["title"], "rows": len(contents["rows"]),
                           "verified": "body folios and divider folios identical with and without it"}
                          if contents else None),
        "passes": log,
        "final_proofs": proofs,
    }
    report_path = Path(output_dir) / f"{manifest['bundle_id']}.volumes.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def render_volumes(
    manifest: dict[str, Any],
    output_dir: Path,
    *,
    manifest_path: Path | None = None,
    draft: bool = False,
    **render_kwargs: Any,
) -> dict[str, Any]:
    """Render every volume, seat the folios, and (if asked) add the contents of the work."""
    parts = split_manifest(
        manifest,
        base=Path(manifest_path).resolve().parent if manifest_path else None,
        generated_dir=Path(output_dir) / "generated",
    )
    render_cfg = manifest.get("render") or {}
    contents_cfg = render_cfg.get("work_contents")
    if isinstance(contents_cfg, bool):
        contents_cfg = {"enabled": contents_cfg}
    want_contents = bool((contents_cfg or {}).get("enabled", False))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    passes = passes_config(render_cfg)

    def one(part: dict[str, Any], start: int, pass_name: str, as_draft: bool,
            contents: dict[str, Any] | None) -> VolumeRender:
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
        return VolumeRender(
            id=part["volume"]["id"], number=part["volume"]["number"], title=part["volume"]["title"],
            render_id=plan.render_id, pdf=str(pdf), pages=pages, first_body_folio=first,
            last_body_folio=last, divider_folios=_divider_folios(out_dir, plan.render_id, pdf, part),
        )

    def run(pass_name: str, as_draft: bool, contents: dict[str, Any] | None) -> list[VolumeRender]:
        """A measuring pass: in order, each volume seated after the one before."""
        results: list[VolumeRender] = []
        start = 1
        for part in parts:
            results.append(one(part, start, pass_name, as_draft, contents))
            start = results[-1].last_body_folio + 1
        return results

    if passes is not None:
        return _planned(parts, passes, one, run, want_contents, contents_cfg, manifest, output_dir)

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
