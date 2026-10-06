"""The work render loop and references across volumes (map step 6; engine/work_render.py, work_refs.py)."""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from engine import work_render
from engine.manifest_compiler import CompositeBundleCompiler
from engine.volumes import VolumeError, split_manifest
from engine.work_refs import WorkRefError, canonical, key_of, missing, normalize, refs_in, resolve
from engine.work_render import WorkVolume, render_work, work_manifest_errors


# --- the reference grammar ------------------------------------------------------------


def test_normalize_folds_case_punctuation_and_quotes():
    assert normalize("The Reset That Wasn’t a Reset") == normalize("the reset that wasn't  a reset")
    assert normalize("Encore — Witnesses") == "encore witnesses"


def test_keys_and_refs():
    assert canonical("iii:Contents in Detail") == "iii:contents in detail"
    assert canonical("ii:divider:Part-Two") == "ii:divider:Part-Two"
    assert key_of("i", "Overture") == "i:overture"
    text = r"a \OFWorkRef{i:Overture} b \OFWorkRef[00]{iii:Notes} c \OFWorkRef{i:overture}"
    assert refs_in(text) == ["i:overture", "iii:notes"]
    with pytest.raises(WorkRefError):
        canonical("no-volume")


def test_resolve_uses_labels_then_the_placeholder_and_records_what_it_used():
    text = r"\OFWorkRef{i:Overture}/\OFWorkRef[00]{iii:Notes}/\OFWorkRef{iii:Glossary}/\setcounter{page}{\OFWorkSeat}"
    out, used = resolve(text, {"i:overture": "1", "iii:notes": "498"}, placeholder="000", seat=487)
    assert out == r"1/498/000/\setcounter{page}{487}"
    assert used == {"i:overture": "1", "iii:notes": "498", "iii:glossary": None}
    out, _ = resolve(r"\OFWorkRef[00]{iii:Notes}", {}, placeholder="000")
    assert out == "00"
    with pytest.raises(WorkRefError, match="OFWorkSeat"):
        resolve(r"\OFWorkSeat", {})
    assert resolve(r"\OFWorkSeatX", {})[0] == r"\OFWorkSeatX"  # another macro, not the token


def test_missing_names_why():
    table = {"i:overture": "1", "i:@ambiguous": "i:twice"}
    assert missing({"i:overture": "1"}, table, {"i"}) == []
    out = missing({"ii:x": None, "i:twice": None, "i:nope": None}, table, {"i"})
    assert "no volume 'ii'" in out[0] and "more than once" in out[1] and "no outline entry" in out[2]


# --- the loop, with a fake renderer ------------------------------------------------------


class FakeBook:
    """Volumes of fixed size; each cites keys; a label is its volume's seat plus an offset.

    ``grow`` makes a volume one page longer once a citation in it resolves, to
    exercise the shape gate.
    """

    def __init__(self, spec):
        self.spec = spec        # vid -> {"pages": n, "titles": {title: offset}, "cites": [keys], "grow": bool}
        self.renders: list[tuple[str, bool]] = []

    def install(self, monkeypatch):
        def render_one(part, manifest_path, out_dir, **kwargs):
            vol = part["volume"]
            vid, start, labels = vol["id"], vol["body_folio_start"], vol["work_labels"]
            used = {k: labels.get(k) for k in self.spec[vid]["cites"]}
            self.renders.append((vid, bool(kwargs.get("draft"))))
            pages = self.spec[vid]["pages"] + (1 if self.spec[vid].get("grow") and any(used.values()) else 0)
            pdf = f"{out_dir}/{vid}.pdf"
            self.pdfs[pdf] = (vid, start, pages)
            plan = SimpleNamespace(render_id=vid, boundary_assertions={"volume": {"work_refs": used}})
            return plan, {"output": {"pdf_path": pdf}}

        self.pdfs = {}
        monkeypatch.setattr(work_render, "_render_one", render_one)
        monkeypatch.setattr(work_render, "body_folio_span",
                            lambda pdf: (self.pdfs[str(pdf)][2], self.pdfs[str(pdf)][1],
                                         self.pdfs[str(pdf)][1] + self.pdfs[str(pdf)][2] - 1))
        monkeypatch.setattr(work_render, "_divider_folios", lambda *a: [])

        def harvest(vid, pdf, dividers=None):
            _, start, _ = self.pdfs[str(pdf)]
            return {key_of(vid, t): str(start + off) for t, off in self.spec[vid]["titles"].items()}

        monkeypatch.setattr(work_render, "harvest", harvest)

    def volumes(self):
        n = len(self.spec)
        return [WorkVolume(manifest={"kind": "composite_bundle"}, manifest_path=None, id=vid, number=i,
                           count=n, title=f"V{i}") for i, vid in enumerate(self.spec, start=1)]


def test_every_volume_cites_every_other_and_the_loop_closes(tmp_path, monkeypatch):
    spec = {vid: {"pages": 10, "titles": {f"T{vid}": 3}, "cites": [f"{w}:t{w}" for w in "abcd"]} for vid in "abcd"}
    book = FakeBook(spec)
    book.install(monkeypatch)
    report = render_work(book.volumes(), tmp_path, work_id="w")
    vols = {v["id"]: v for v in report["volumes"]}
    assert [vols[v]["first_body_folio"] for v in "abcd"] == [1, 11, 21, 31]
    # Every citation resolved to the label the cited volume has.
    assert vols["a"]["refs"] == {"a:ta": "4", "b:tb": "14", "c:tc": "24", "d:td": "34"}
    assert all(v["refs"] == vols["a"]["refs"] for v in vols.values())
    # Seat pass, then one pass re-renders exactly the volumes that cited a later (or their own) label.
    assert [p["rendered"] for p in report["passes"]] == [list("abcd"), list("abcd")]
    assert report["fixed_point"]["passes"] == 2


def test_a_volume_that_cites_only_earlier_volumes_is_not_rendered_again(tmp_path, monkeypatch):
    spec = {"a": {"pages": 5, "titles": {"A": 0}, "cites": []},
            "b": {"pages": 5, "titles": {"B": 0}, "cites": ["a:a"]},
            "c": {"pages": 5, "titles": {"C": 0}, "cites": ["a:a", "c:c"]}}
    book = FakeBook(spec)
    book.install(monkeypatch)
    report = render_work(book.volumes(), tmp_path, work_id="w")
    assert [p["rendered"] for p in report["passes"]] == [["a", "b", "c"], ["c"]]


def test_a_volume_that_changes_shape_stops_the_build(tmp_path, monkeypatch):
    spec = {"a": {"pages": 5, "titles": {"A": 0}, "cites": ["b:b"], "grow": True},
            "b": {"pages": 5, "titles": {"B": 0}, "cites": []}}
    book = FakeBook(spec)
    book.install(monkeypatch)
    with pytest.raises(VolumeError, match="changed shape.*no retry"):
        render_work(book.volumes(), tmp_path, work_id="w")


def test_an_unresolvable_reference_fails_by_name(tmp_path, monkeypatch):
    spec = {"a": {"pages": 5, "titles": {"A": 0}, "cites": ["b:nothing", "z:x"]},
            "b": {"pages": 5, "titles": {"B": 0}, "cites": []}}
    book = FakeBook(spec)
    book.install(monkeypatch)
    with pytest.raises(VolumeError, match=r"b:nothing.*no outline entry.*z:x.*no volume 'z'"):
        render_work(book.volumes(), tmp_path, work_id="w")


def test_max_passes_bounds_the_loop(tmp_path, monkeypatch):
    spec = {"a": {"pages": 5, "titles": {"A": 0}, "cites": ["b:b"]},
            "b": {"pages": 5, "titles": {"B": 0}, "cites": []}}
    book = FakeBook(spec)
    book.install(monkeypatch)
    with pytest.raises(VolumeError, match="no fixed point after 1 passes"):
        render_work(book.volumes(), tmp_path, work_id="w", render_cfg={"refs": {"max_passes": 1}})


def test_planned_passes_draft_the_loop_then_render_each_final_once(tmp_path, monkeypatch):
    spec = {"a": {"pages": 5, "titles": {"A": 0}, "cites": ["b:b"]},
            "b": {"pages": 5, "titles": {"B": 0}, "cites": ["a:a"]}}
    book = FakeBook(spec)
    book.install(monkeypatch)
    monkeypatch.setattr("engine.pass_gates.compare_renders", lambda a, b: [])
    report = render_work(book.volumes(), tmp_path, work_id="w", render_cfg={"passes": {"final_parallel": 2}},
                         bake_images=True)
    kinds = [p.get("kind", p["pass"]) for p in report["passes"]]
    assert kinds == ["seat", "refs", "final", "prove"]
    # Seat pass a, b (drafts); only a cited a later volume, so only a re-drafts; then each final once.
    assert book.renders[:3] == [("a", True), ("b", True), ("a", True)]
    assert sorted(book.renders[3:]) == [("a", False), ("b", False)]
    assert all(v["pdf"].startswith(str(tmp_path / f"vol-{v['id']}") + "/") for v in report["volumes"])
    assert all(p["same_shape"] for p in report["final_proofs"])


def test_work_manifest_schema(tmp_path):
    (tmp_path / "a.yaml").write_text("x: 1\n")
    good = {"kind": "work", "schema_version": "work_manifest_v1", "work_id": "w1",
            "volumes": [{"id": "i", "manifest": "a.yaml"}, {"id": "ii", "manifest": "a.yaml", "seat": "source"}]}
    assert work_manifest_errors(good, base=tmp_path) == []
    bad = {**good, "volumes": [{"id": "i", "manifest": "a.yaml"}, {"id": "i", "manifest": "nope.yaml", "seat": "x"}]}
    errors = work_manifest_errors(bad, base=tmp_path)
    assert any("seat" in e for e in errors)
    bad["volumes"][1]["seat"] = "auto"
    errors = work_manifest_errors(bad, base=tmp_path)
    assert any("repeated" in e for e in errors) and any("does not exist" in e for e in errors)


# --- the compiler ------------------------------------------------------------------------


def _bundle(tmp_path: Path, name: str, text: str, *, profile: str = "keeper") -> dict:
    path = tmp_path / f"{name}.md"
    path.write_text(f"# {name}\n\n{text}\n", encoding="utf-8")
    return {"kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": name, "profile": profile,
            "presentation": {"title": name, "date": "2026-10-06"},
            "sources": [{"uid": name, "path": str(path), "role": "primary_anchor", "order": 1, "title": name,
                         "include_frontmatter": "none", "suppress_frontmatter": True}],
            "render": {"include_toc": False, "numbersections": False, "emit_visible_provenance": False}}


def test_the_compiler_resolves_references_and_a_source_seat(tmp_path):
    m = _bundle(tmp_path, "one", r"See page \OFWorkRef{ii:Elsewhere} and \OFWorkRef{ii:Nowhere}; seat \OFWorkSeat.")
    m["volume"] = {"id": "i", "number": 1, "count": 2, "body_folio_start": 7, "seat": "source",
                   "work_labels": {"ii:elsewhere": "42"}, "work_ref_placeholder": "00"}
    plan = CompositeBundleCompiler().compile(m)
    text = Path(plan.render_source).read_text(encoding="utf-8")
    assert "See page 42 and 00; seat 7." in text
    assert "OFSeatBodyFolio" not in text and "OFWorkRef" not in text
    assert plan.boundary_assertions["volume"]["seat"] == "source"
    assert plan.boundary_assertions["volume"]["work_refs"] == {"ii:elsewhere": "42", "ii:nowhere": None}


def test_outside_a_work_a_reference_prints_its_placeholder_and_a_seat_is_refused(tmp_path):
    plan = CompositeBundleCompiler().compile(_bundle(tmp_path, "solo", r"p. \OFWorkRef{ii:X}"))
    assert "p. 000" in Path(plan.render_source).read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="OFWorkSeat"):
        CompositeBundleCompiler().compile(_bundle(tmp_path, "seat", r"\OFWorkSeat"))


# --- real renders --------------------------------------------------------------------------

needs_tex = pytest.mark.skipif(
    not (shutil.which("pandoc") and shutil.which("xelatex")), reason="pandoc/xelatex missing"
)


def _three_volume_work(tmp_path: Path) -> dict:
    """Three volumes; the first cites the last, the last cites the first, the middle cites itself."""
    filler = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 40 + "\n\n") * 3
    cites = {1: r"The coda opens on page \OFWorkRef{iii:divider:d5}.",
             3: r"The work opened on page \OFWorkRef{i:divider:d1}, and this part on \OFWorkRef{iii:divider:d5}.",
             2: r"This part opens on page \OFWorkRef{ii:divider:d3}."}
    sources, dividers = [], []
    for i in range(1, 7):
        path = tmp_path / f"s{i}.md"
        extra = cites.get((i + 1) // 2, "") if i % 2 else ""
        path.write_text(f"# Source {i}\n\n{extra}\n\n{filler}", encoding="utf-8")
        sources.append({"uid": f"s{i}", "path": str(path), "role": "primary_anchor", "order": i, "title": f"Source {i}",
                        "include_frontmatter": "none", "suppress_frontmatter": True,
                        "chapter_opener": {"title": f"Source {i}"}, "strip_leading_heading": True})
        if i % 2:
            dividers.append({"uid": f"d{i}", "before_source_uid": f"s{i}", "title": f"Part {(i + 1) // 2}"})
    return {"kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "trio",
            "profile": "keeper", "presentation": {"title": "Trio", "date": "2026-10-06"},
            "sources": sources, "section_dividers": dividers,
            "volumes": [{"id": "i"}, {"id": "ii", "before_source_uid": "s3"}, {"id": "iii", "before_source_uid": "s5"}],
            "render": {"include_toc": False, "numbersections": False, "emit_visible_provenance": False,
                       "work_contents": True, "delivery": {"mode": "bound", "binding": "perfect", "duplex": True}}}


@needs_tex
def test_three_volumes_citing_each_other_both_ways(tmp_path):
    fitz = pytest.importorskip("fitz")
    report = work_render.render_split_work(_three_volume_work(tmp_path), tmp_path / "out")
    one, two, three = report["volumes"]
    assert two["first_body_folio"] == one["last_body_folio"] + 1
    assert three["first_body_folio"] == two["last_body_folio"] + 1
    folio = {d["uid"]: d["folio"] for v in report["volumes"] for d in v["divider_folios"]}
    text = {v["id"]: " ".join(" ".join(p.get_text() for p in fitz.open(v["pdf"])).split()) for v in report["volumes"]}
    assert f"The coda opens on page {folio['d5']}." in text["i"]
    assert f"The work opened on page {folio['d1']}, and this part on {folio['d5']}." in text["iii"]
    assert f"This part opens on page {folio['d3']}." in text["ii"]
    assert "000" not in text["i"] + text["ii"] + text["iii"]
    assert report["fixed_point"]["passes"] == 2
    saved = yaml.safe_load(Path(report["report_path"]).read_text())
    assert saved["schema_version"] == "work_run_v1"


@needs_tex
def test_a_work_manifest_of_separate_bundles_with_a_source_seated_volume(tmp_path):
    fitz = pytest.importorskip("fitz")
    filler = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 40 + "\n\n") * 3
    first = _bundle(tmp_path, "first", r"The second volume begins on page \OFWorkRef{second:divider:start}." + "\n\n" + filler)
    second = _bundle(tmp_path, "second", filler)
    seat = tmp_path / "seat.md"
    # The volume owns its folio contract: roman front matter (so the PDF carries page
    # labels), then the body seated where the work says it starts.
    seat.write_text("```{=latex}\n\\pagenumbering{roman}\n\\OFSeatBodyFolio{\\OFWorkSeat}\n```\n",
                    encoding="utf-8")
    second["sources"][0]["order"] = 2
    second["sources"].insert(0, {"uid": "seat", "path": str(seat), "role": "primary_anchor", "order": 1,
                                 "include_frontmatter": "none", "suppress_frontmatter": True})
    second["section_dividers"] = [{"uid": "start", "before_source_uid": "second", "title": "Second"}]
    for m in (first, second):
        m["render"]["delivery"] = {"mode": "bound", "binding": "perfect", "duplex": True}
        (tmp_path / f"{m['bundle_id']}.yaml").write_text(yaml.safe_dump(m), encoding="utf-8")
    work = {"kind": "work", "schema_version": "work_manifest_v1", "work_id": "pair",
            "volumes": [{"id": "first", "manifest": "first.yaml", "dir": "vol1"},
                        {"id": "second", "manifest": "second.yaml", "dir": "vol2", "seat": "source"}],
            "render": {"passes": {"final_parallel": 2}}}
    (tmp_path / "pair.work.yaml").write_text(yaml.safe_dump(work), encoding="utf-8")
    report = work_render.render_work_manifest(work, tmp_path / "pair.work.yaml", tmp_path / "out")
    one, two = report["volumes"]
    assert two["first_body_folio"] == one["last_body_folio"] + 1
    assert Path(one["pdf"]).parent.name == "vol1" and Path(two["pdf"]).parent.name == "vol2"
    assert (tmp_path / "out" / "vol1_draft").is_dir()
    start = two["divider_folios"][0]["folio"]
    text = " ".join(" ".join(p.get_text() for p in fitz.open(one["pdf"])).split())
    assert f"The second volume begins on page {start}." in text
    assert all(p["same_shape"] for p in report["final_proofs"])
