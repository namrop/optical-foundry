"""The work render loop: any number of volumes that cite each other (promotion map step 6).

Ruling 01a100da-3cde: "the engine should be able to handle the build order loop.
as an option that supports an arbitrary number of volumes." Codex 0 did this in
its shell build as a fixed sequence of passes (A, B, C, D, G, W, H): the reading
volumes cite Volume III and Volume III cites them, so each side had to render
before the other could name its pages. This module is that loop, for N volumes
and any pattern of citation, and it replaces ``render_volumes`` and ``_planned``.

A work is an ordered list of volumes, each an ordinary bundle manifest. It comes
from a bundle manifest with ``volumes:`` (``engine.volumes.split_manifest``) or
from a work manifest (``kind: work``, ``schemas/work_manifest_v1.yaml``) that
names one bundle manifest per volume.

How it runs:

1. **Seat pass.** The volumes render in order; each body starts at the folio
   after the previous volume's last (B1). After each render the engine harvests
   that volume's labels: every outline entry and divider, with the PDF page
   label it falls on (``engine/work_refs.py``). A later volume in the same pass
   already sees an earlier volume's labels; anything not yet rendered resolves to
   a placeholder of the same width.
2. **Re-render what is stale.** A volume is stale when a label it cited is not
   the label the work now has. Stale volumes re-render, in parallel (their seats
   are fixed), until none is: then every volume was rendered with exactly the
   labels the work offers. That is the fixed point.
3. **The shape is fixed after the seat pass.** A re-render that changes a
   volume's page count or body folios is refused, not retried: the other volumes
   cite its labels and seat on its last folio, and past a moved folio a fixed
   point is not guaranteed to exist (Codex 0's C3, D1c and G3, one rule now).
   ``refs.max_passes`` bounds the loop all the same.
4. **Final wave** (with ``passes``, B3): the passes above render in draft (image
   boxes, no image data); the finals then render once, full, ``final_parallel``
   at a time, and each is proved against its last draft (page count, every
   label, the outline). Without ``passes`` every render is full and the last
   render of each volume is its final.

A reference to a label the finished work does not have (no such volume, title or
divider, or a title that occurs twice in its volume) fails the build by name.
"""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.volumes import VolumeError, roman
from engine.work_refs import DEFAULT_PLACEHOLDER, harvest, key_of, missing

DEFAULT_MAX_PASSES = 4
SEAT_MODES = ("auto", "source")


@dataclass
class WorkVolume:
    """One volume of a work: an ordinary bundle manifest and where it sits."""

    manifest: dict[str, Any]
    manifest_path: Path | None
    id: str
    number: int
    count: int
    title: str
    dir: str = ""
    seat: str = "auto"     # auto: the engine or template seats the body; source: the volume's sources do

    def __post_init__(self) -> None:
        self.dir = self.dir or f"vol-{self.id}"
        if self.seat not in SEAT_MODES:
            raise VolumeError(f"volume {self.id}: seat must be one of {SEAT_MODES}, not {self.seat!r}")


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
    refs: dict[str, str | None] = field(default_factory=dict)
    evidence_status: str = "ok"

    def shape(self) -> tuple[int, int, int]:
        return self.pages, self.first_body_folio, self.last_body_folio


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def passes_config(render_cfg: dict[str, Any]) -> dict[str, Any] | None:
    """B3: ``render.passes`` — draft measuring passes and one final wave (optional, as ruled).

    ``{final_parallel: N, prove_final: true}``. Without it every render is full.
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


def refs_config(render_cfg: dict[str, Any]) -> dict[str, Any]:
    cfg = render_cfg.get("refs") or {}
    if not isinstance(cfg, dict):
        raise VolumeError("render.refs must be a mapping, e.g. {placeholder: '000', max_passes: 4}")
    max_passes = int(cfg.get("max_passes", DEFAULT_MAX_PASSES))
    if max_passes < 1:
        raise VolumeError("render.refs.max_passes must be at least 1")
    return {"placeholder": str(cfg.get("placeholder", DEFAULT_PLACEHOLDER)), "max_passes": max_passes}


def contents_config(render_cfg: dict[str, Any]) -> dict[str, Any] | None:
    cfg = render_cfg.get("work_contents")
    if isinstance(cfg, bool):
        cfg = {"enabled": cfg}
    if not (cfg or {}).get("enabled", False):
        return None
    return {"title": cfg.get("title") or "Contents of the Work"}


# --------------------------------------------------------------------------
# Work manifests (kind: work)
# --------------------------------------------------------------------------

WORK_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "work_manifest_v1.yaml"


def work_manifest_errors(manifest: dict[str, Any], *, base: Path | None = None) -> list[str]:
    import yaml
    from jsonschema import Draft202012Validator

    schema = yaml.safe_load(WORK_SCHEMA_PATH.read_text(encoding="utf-8"))
    normalized = json.loads(json.dumps(manifest, default=str))
    errors = [
        f"schema: {'/'.join(str(p) for p in e.absolute_path) or '(top)'}: {e.message}"
        for e in sorted(Draft202012Validator(schema).iter_errors(normalized), key=lambda e: list(e.absolute_path))
    ]
    if errors:
        return errors
    ids: set[str] = set()
    dirs: set[str] = set()
    for i, vol in enumerate(manifest["volumes"]):
        if vol["id"] in ids:
            errors.append(f"volumes[{i}].id {vol['id']!r} is repeated")
        ids.add(vol["id"])
        d = vol.get("dir") or f"vol-{vol['id']}"
        if d in dirs:
            errors.append(f"volumes[{i}].dir {d!r} is repeated")
        dirs.add(d)
        if base is not None and not (base / vol["manifest"]).is_file():
            errors.append(f"volumes[{i}].manifest {vol['manifest']!r} does not exist")
    return errors


def volumes_from_work_manifest(manifest: dict[str, Any], manifest_path: Path) -> list[WorkVolume]:
    """The volumes a work manifest names, each validated as the bundle it is."""
    import yaml

    from engine.manifest_compiler import bundle_schema_errors

    base = manifest_path.resolve().parent
    errors = work_manifest_errors(manifest, base=base)
    if errors:
        raise VolumeError("; ".join(errors))
    out = []
    count = len(manifest["volumes"])
    for n, vol in enumerate(manifest["volumes"], start=1):
        path = (base / vol["manifest"]).resolve()
        bundle = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(bundle, dict):
            raise VolumeError(f"volume {vol['id']}: {path} is not a manifest")
        if bundle.get("volumes") or bundle.get("volume"):
            raise VolumeError(f"volume {vol['id']}: {path.name} must be one volume's bundle, "
                              "without volumes: or volume: (the work manifest says where it sits)")
        bad = bundle_schema_errors(bundle)
        if bad:
            raise VolumeError(f"volume {vol['id']}: {path.name}: " + "; ".join(bad[:5]))
        out.append(WorkVolume(manifest=bundle, manifest_path=path, id=vol["id"], number=n, count=count,
                              title=vol.get("title") or f"Volume {roman(n)}", dir=vol.get("dir") or "",
                              seat=vol.get("seat", "auto")))
    return out


def volumes_from_split(parts: list[dict[str, Any]], manifest_path: Path | None) -> list[WorkVolume]:
    """The volumes ``split_manifest`` cut from one bundle manifest with ``volumes:``."""
    return [
        WorkVolume(manifest=part, manifest_path=manifest_path, id=part["volume"]["id"],
                   number=part["volume"]["number"], count=part["volume"]["count"], title=part["volume"]["title"])
        for part in parts
    ]


# --------------------------------------------------------------------------
# One render
# --------------------------------------------------------------------------

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
        if not label:
            raise VolumeError(f"{render_id}: divider {uid} is on page {page}, which has no page label")
        # Divider kinds may own frontmatter pages too. Preserve their PDF label
        # exactly, just as harvest already does for outline entries.
        rows.append({"uid": uid, "title": titles.get(uid, uid), "folio": int(label) if label.isdigit() else label, "page": int(page)})
    return rows


def _compiler_for(manifest: dict[str, Any]):
    from engine.manifest_compiler import CAMStackCompiler, CodexBundleCompiler, CompositeBundleCompiler

    return {"composite_bundle": CompositeBundleCompiler, "cam_stack": CAMStackCompiler,
            "codex_bundle": CodexBundleCompiler}[manifest["kind"]]


def _render_one(manifest: dict[str, Any], manifest_path: Path | None, out_dir: Path, **render_kwargs: Any):
    from renderers.pandoc_renderer import PandocRenderer

    plan = _compiler_for(manifest)().compile(manifest, manifest_path=manifest_path)
    evidence = PandocRenderer().render(plan, output_dir=str(out_dir), **render_kwargs)
    if evidence.get("status") == "error":
        raise VolumeError(f"{plan.render_id}: render failed: {evidence.get('error')}")
    return plan, evidence


def _contents_rows(volumes: list[WorkVolume]) -> list[dict[str, Any]]:
    """B2: every divider of every volume, each citing its own folio."""
    return [
        {"volume": v.id, "volume_title": v.title, "volume_label": f"Vol.\u00a0{roman(v.number)}",
         "title": d.get("title") or d.get("uid"), "uid": d["uid"], "ref": key_of(v.id, f"divider:{d['uid']}")}
        for v in volumes for d in v.manifest.get("section_dividers") or [] if d.get("uid")
    ]


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

def render_work(
    volumes: list[WorkVolume],
    output_dir: Path,
    *,
    work_id: str,
    render_cfg: dict[str, Any] | None = None,
    draft: bool = False,
    **render_kwargs: Any,
) -> dict[str, Any]:
    """Render every volume until each cites the labels the work has; then the finals."""
    if len(volumes) < 2:
        raise VolumeError("a work has at least two volumes")
    render_cfg = render_cfg or {}
    passes = passes_config(render_cfg)
    refs = refs_config(render_cfg)
    contents = contents_config(render_cfg)
    rows = _contents_rows(volumes) if contents else None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ids = {v.id for v in volumes}

    table: dict[str, str] = {}
    latest: dict[str, VolumeRender] = {}
    first_shape: dict[str, tuple[int, int, int]] = {}
    log: list[dict[str, Any]] = []

    def one(vol: WorkVolume, start: int, labels: dict[str, str], *, measuring: bool) -> tuple[VolumeRender, dict[str, str]]:
        part = copy.deepcopy(vol.manifest)
        block = dict(part.get("volume") or {})
        block.update({"id": vol.id, "number": vol.number, "count": vol.count, "title": vol.title,
                      "body_folio_start": start, "work_labels": dict(labels),
                      "work_ref_placeholder": refs["placeholder"]})
        if vol.seat != "auto":
            block["seat"] = vol.seat
        if rows is not None:
            block["work_contents"] = {"title": contents["title"], "rows": rows}
        part["volume"] = block
        if passes is not None and measuring:
            out_dir, kwargs = output_dir / f"{vol.dir}_draft", {"draft": True}
        else:
            out_dir, kwargs = output_dir / vol.dir, {"draft": draft, **render_kwargs}
        plan, evidence = _render_one(part, vol.manifest_path, out_dir, **kwargs)
        pdf = Path(evidence["output"]["pdf_path"])
        pages, first, last = body_folio_span(pdf)
        if first != start:
            raise VolumeError(f"{plan.render_id}: body starts at folio {first}, seated at {start}")
        dividers = _divider_folios(out_dir, plan.render_id, pdf, part)
        used = dict(((plan.boundary_assertions.get("volume") or {}).get("work_refs") or {}))
        result = VolumeRender(id=vol.id, number=vol.number, title=vol.title, render_id=plan.render_id,
                              pdf=str(pdf), pages=pages, first_body_folio=first, last_body_folio=last,
                              divider_folios=dividers, refs=used)
        return result, harvest(vol.id, pdf, dividers)

    def take(vol: WorkVolume, result: VolumeRender, offered: dict[str, str]) -> None:
        for key in [k for k in table if k.split(":", 1)[0] == vol.id]:
            del table[key]
        table.update(offered)
        latest[vol.id] = result

    # 1. The seat pass: in order, each volume after the one before.
    start = 1
    for vol in volumes:
        result, offered = one(vol, start, table, measuring=True)
        take(vol, result, offered)
        first_shape[vol.id] = result.shape()
        start = result.last_body_folio + 1
    log.append({"pass": 1, "kind": "seat", "draft": passes is not None, "rendered": [v.id for v in volumes]})

    # 2. Re-render what is stale until nothing is.
    workers = passes["final_parallel"] if passes else 1
    n = 1
    while True:
        stale = [v for v in volumes if any(table.get(k) != val for k, val in latest[v.id].refs.items())]
        if not stale:
            break
        if n >= refs["max_passes"]:
            raise VolumeError(
                f"no fixed point after {n} passes (render.refs.max_passes): still stale: "
                + ", ".join(v.id for v in stale))
        n += 1
        snapshot = dict(table)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            done = list(pool.map(lambda v: one(v, first_shape[v.id][1], snapshot, measuring=True), stale))
        for vol, (result, offered) in zip(stale, done):
            if result.shape() != first_shape[vol.id]:
                (p0, a0, b0), (p1, a1, b1) = first_shape[vol.id], result.shape()
                raise VolumeError(
                    f"volume {vol.id} changed shape when re-rendered with the work's labels "
                    f"(pages {p0} -> {p1}, body {a0}-{b0} -> {a1}-{b1}). The other volumes seat on its "
                    "folios and cite its labels, so the build stops; there is no retry. A citation "
                    "whose placeholder is narrower or wider than its label can do this: give it a "
                    "placeholder of the label's width (\\OFWorkRef[placeholder]{key}).")
            take(vol, result, offered)
        log.append({"pass": n, "kind": "refs", "draft": passes is not None, "rendered": [v.id for v in stale]})

    unresolved = {v.id: missing(latest[v.id].refs, table, ids) for v in volumes}
    unresolved = {k: v for k, v in unresolved.items() if v}
    if unresolved:
        raise VolumeError("references the work cannot resolve: " + "; ".join(
            f"volume {vid}: {', '.join(keys)}" for vid, keys in unresolved.items()))

    # 3. The final wave (B3) and its proofs.
    proofs: list[dict[str, Any]] = []
    if passes is not None:
        drafts = dict(latest)
        snapshot = dict(table)
        with ThreadPoolExecutor(max_workers=passes["final_parallel"]) as pool:
            finals = list(pool.map(lambda v: one(v, first_shape[v.id][1], snapshot, measuring=False)[0], volumes))
        log.append({"pass": n + 1, "kind": "final", "draft": False, "parallel": passes["final_parallel"],
                    "rendered": [v.id for v in volumes]})
        if passes["prove_final"]:
            from engine.pass_gates import compare_renders

            for f in finals:
                diffs = compare_renders(Path(drafts[f.id].pdf), Path(f.pdf))
                if f.refs != drafts[f.id].refs:
                    diffs.append("the final resolved its references differently from its draft")
                proofs.append({"volume": f.id, "same_shape": not diffs, "differences": diffs[:10]})
            log.append({"pass": "prove", "ok": all(p["same_shape"] for p in proofs)})
            bad = [p for p in proofs if not p["same_shape"]]
            if bad:
                raise VolumeError("a final volume does not have its draft's shape: "
                                  + "; ".join(f"{p['volume']}: {p['differences'][0]}" for p in bad))
        latest = {f.id: f for f in finals}

    report: dict[str, Any] = {
        "schema_version": "work_run_v1",
        "work_id": work_id,
        "volumes": [latest[v.id].__dict__ for v in volumes],
        "passes": log,
        "fixed_point": {"passes": n, "labels": len([k for k in table if "@" not in k]),
                        "references": sum(len(latest[v.id].refs) for v in volumes)},
        "final_proofs": proofs,
        "work_contents": ({"title": contents["title"], "rows": len(rows)} if contents else None),
    }
    report_path = output_dir / f"{work_id}.work.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def render_split_work(manifest: dict[str, Any], output_dir: Path, *, manifest_path: Path | None = None,
                      draft: bool = False, **render_kwargs: Any) -> dict[str, Any]:
    """A bundle manifest with ``volumes:``: split it, then run the loop."""
    from engine.volumes import split_manifest

    parts = split_manifest(manifest, base=Path(manifest_path).resolve().parent if manifest_path else None,
                           generated_dir=Path(output_dir) / "generated")
    return render_work(volumes_from_split(parts, manifest_path), output_dir, work_id=manifest["bundle_id"],
                       render_cfg=manifest.get("render") or {}, draft=draft, **render_kwargs)


def render_work_manifest(manifest: dict[str, Any], manifest_path: Path, output_dir: Path, *,
                         draft: bool = False, **render_kwargs: Any) -> dict[str, Any]:
    """A work manifest (``kind: work``): its volumes, then the loop."""
    volumes = volumes_from_work_manifest(manifest, manifest_path)
    return render_work(volumes, output_dir, work_id=manifest["work_id"], render_cfg=manifest.get("render") or {},
                       draft=draft, **render_kwargs)
