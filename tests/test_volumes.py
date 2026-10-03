"""B1 volumes and B2 contents of the work (engine/volumes.py; promotion map, step 3)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from engine.manifest_compiler import CompositeBundleCompiler
from engine.selection import SelectionError, select
from engine.volumes import VolumeError, body_folio_span, render_volumes, roman, split_manifest, volume_errors


def _work(tmp_path: Path, n: int = 4, *, profile: str = "keeper", paragraphs: int = 1) -> dict:
    text = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 40 + "\n\n") * paragraphs
    sources, dividers = [], []
    for i in range(1, n + 1):
        path = tmp_path / f"s{i}.md"
        path.write_text(f"# Source {i}\n\n{text}", encoding="utf-8")
        sources.append({"uid": f"s{i}", "path": str(path), "role": "primary_anchor", "order": i, "title": f"Source {i}",
                        "include_frontmatter": "none", "suppress_frontmatter": True,
                        "chapter_opener": {"title": f"Source {i}"}, "strip_leading_heading": True})
        if i % 2 == 1:
            dividers.append({"uid": f"d{i}", "before_source_uid": f"s{i}", "title": f"Part {(i + 1) // 2}"})
    return {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "vols", "profile": profile,
        "presentation": {"title": "Volumes", "date": "2026-10-01"},
        "sources": sources, "section_dividers": dividers,
        "volumes": [{"id": "i"}, {"id": "ii", "before_source_uid": "s3"}],
        "render": {"include_toc": False, "numbersections": False, "emit_visible_provenance": False,
                   "work_contents": True, "delivery": {"mode": "bound", "binding": "perfect", "duplex": True}},
    }


def test_roman():
    assert [roman(n) for n in (1, 4, 9, 14, 40)] == ["I", "IV", "IX", "XIV", "XL"]


def test_split_gives_each_volume_its_sources_and_dividers(tmp_path):
    parts = split_manifest(_work(tmp_path))
    assert [p["bundle_id"] for p in parts] == ["vols-vol-i", "vols-vol-ii"]
    assert [[s["uid"] for s in p["sources"]] for p in parts] == [["s1", "s2"], ["s3", "s4"]]
    assert [[d["uid"] for d in p["section_dividers"]] for p in parts] == [["d1"], ["d3"]]
    assert parts[1]["volume"] == {"id": "ii", "number": 2, "count": 2, "title": "Volume II"}
    assert parts[1]["presentation"]["subtitle"] == "Volume II"
    assert all("volumes" not in p for p in parts)
    for part in parts:  # each is an ordinary, valid bundle manifest
        assert CompositeBundleCompiler().validate(part) == []


@pytest.mark.parametrize(
    "volumes, needle",
    [
        ([{"id": "i"}, {"id": "ii", "before_source_uid": "nope"}], "not a source uid"),
        ([{"id": "i"}, {"id": "ii", "before_source_uid": "s3"}, {"id": "iii", "before_source_uid": "s2"}], "starts before"),
        ([{"id": "i"}, {"id": "i", "before_source_uid": "s3"}], "repeated"),
        ([{"id": "i", "before_source_uid": "s2"}, {"id": "ii", "before_source_uid": "s3"}], "first source"),
    ],
)
def test_bad_volume_cuts_are_validation_errors(tmp_path, volumes, needle):
    manifest = _work(tmp_path)
    manifest["volumes"] = volumes
    assert any(needle in e for e in volume_errors(manifest))
    assert any(needle in e for e in CompositeBundleCompiler().validate(manifest))
    with pytest.raises(VolumeError):
        split_manifest(manifest)


def test_a_whole_work_cannot_be_compiled_as_one_bundle(tmp_path):
    with pytest.raises(ValueError, match="several volumes"):
        CompositeBundleCompiler().compile(_work(tmp_path))


def test_generic_seat_and_roman_front_matter(tmp_path):
    part = split_manifest(_work(tmp_path))[1]
    part["volume"]["body_folio_start"] = 7
    plan = CompositeBundleCompiler().compile(part)
    text = Path(plan.render_source).read_text(encoding="utf-8")
    assert "\\OFSeatBodyFolio{7}" in text
    assert "\\pagenumbering{roman}" in text.split("\n---\n")[0]
    assert text.index("\\OFSeatBodyFolio{7}") < text.index("Part 2")
    assert plan.boundary_assertions["volume"]["seat"] == "engine"


def test_a_template_that_seats_folios_gets_the_variable(tmp_path):
    part = split_manifest(_work(tmp_path, profile="codex0"))[1]
    part["volume"]["body_folio_start"] = 207
    plan = CompositeBundleCompiler().compile(part)
    text = Path(plan.render_source).read_text(encoding="utf-8")
    assert "OFSeatBodyFolio" not in text
    assert "body_folio_start: 207" in text
    assert plan.boundary_assertions["volume"]["seat"] == "template"


def _selection(tmp_path: Path, volumes) -> dict:
    root = tmp_path / "notes"
    root.mkdir()
    for month, words in [(1, 900), (2, 100), (3, 100), (4, 900), (5, 100), (6, 100)]:
        (root / f"n{month}.md").write_text(
            f"---\ncreated: 2026-{month:02d}-10\n---\n# Note {month}\n\n" + "word " * words, encoding="utf-8"
        )
    return {"kind": "selection", "schema_version": "selection_manifest_v1", "selection_id": "vol-test",
            "select": {"roots": [str(root)]}, "group": {"by": "month"}, "volumes": volumes,
            "bundle": {"profile": "keeper"}}


def test_selection_splits_whole_groups_balanced_by_length(tmp_path):
    spec = _selection(tmp_path, {"count": 2, "subtitle": "{span}"})
    manifest = select(spec, spec_path=tmp_path / "s.yaml").manifest
    vols = manifest["volumes"]
    assert [v["title"] for v in vols] == ["Volume I", "Volume II"]
    assert vols[0]["subtitle"] == "January 2026 – March 2026"
    first_of_ii = next(s for s in manifest["sources"] if s["uid"] == vols[1]["before_source_uid"])
    assert first_of_ii["title"] == "Note 4"
    assert CompositeBundleCompiler().validate(manifest) == []


def test_selection_volumes_by_group_key(tmp_path):
    spec = _selection(tmp_path, [{"title": "Winter"}, {"from": "2026-03", "title": "Spring"}])
    vols = select(spec, spec_path=tmp_path / "s.yaml").manifest["volumes"]
    assert [v["title"] for v in vols] == ["Winter", "Spring"]
    spec["volumes"] = [{}, {"from": "2027-01"}]
    with pytest.raises(SelectionError, match="not a group key"):
        select(spec, spec_path=tmp_path / "s.yaml")


needs_tex = pytest.mark.skipif(
    not (shutil.which("pandoc") and shutil.which("xelatex")), reason="pandoc/xelatex missing"
)


@needs_tex
def test_volumes_render_with_continuous_folios_parity_and_contents(tmp_path):
    pytest.importorskip("fitz")
    manifest = _work(tmp_path, paragraphs=3)
    report = render_volumes(manifest, tmp_path / "out")
    one, two = report["volumes"]
    assert one["first_body_folio"] == 1
    assert two["first_body_folio"] == one["last_body_folio"] + 1
    import fitz

    for vol in (one, two):
        labels = [p.get_label() for p in fitz.open(vol["pdf"])]
        first_body = labels.index(str(vol["first_body_folio"]))
        assert all(not label.isdigit() for label in labels[:first_body])  # roman front matter
        assert (first_body + 1) % 2 == vol["first_body_folio"] % 2      # odd folio on an odd page
        assert body_folio_span(Path(vol["pdf"]))[1:] == (vol["first_body_folio"], vol["last_body_folio"])
    assert report["work_contents"]["rows"] == 2
    pages = "\n".join(p.get_text() for p in fitz.open(two["pdf"]))
    assert "Contents of the Work" in pages and "Part 1" in pages and "Part 2" in pages
    saved = yaml.safe_load(Path(report["report_path"]).read_text())
    assert saved["schema_version"] == "volume_run_v1"



# --- B3: planned passes --------------------------------------------------------------


def test_passes_config_is_optional_and_checked():
    from engine.volumes import passes_config

    assert passes_config({}) is None
    assert passes_config({"passes": {"final_parallel": 2}}) == {"final_parallel": 2, "prove_final": True}
    with pytest.raises(VolumeError):
        passes_config({"passes": {"final_parallel": 0}})


def test_planned_passes_draft_then_one_parallel_final_wave_proved_against_the_drafts(tmp_path):
    manifest = _work(tmp_path, paragraphs=3)
    manifest["render"]["passes"] = {"final_parallel": 2}
    report = render_volumes(manifest, tmp_path / "out")
    assert [p["pass"] for p in report["passes"]] == ["seat", "contents", "final", "prove"]
    assert report["passes"][1]["fixed_point"] is True and report["passes"][3]["ok"] is True
    assert all(p["same_shape"] for p in report["final_proofs"])
    one, two = report["volumes"]
    assert two["first_body_folio"] == one["last_body_folio"] + 1
    assert all("/final/" in v["pdf"] for v in report["volumes"])
