"""B4 — a cross-volume endnote sink (promotion map B4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.endnotes import harvest_volume, rewrite_markers
from engine.manifest_compiler import CompositeBundleCompiler
from engine.volumes import VolumeError, split_manifest


def _src(tmp: Path, uid: str, order: int, body: str) -> dict:
    p = tmp / f"{uid}.md"
    p.write_text(f"---\nuid: {uid}\n---\n\n{body}", encoding="utf-8")
    return {"uid": uid, "path": str(p), "role": "primary_anchor", "order": order}


def _work(tmp: Path, **endnotes) -> dict:
    return {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "work", "profile": "keeper",
        "presentation": {"title": "W"},
        "render": {"endnotes": {"sink": "iii", **endnotes}},
        "sources": [
            _src(tmp, "a", 1, "One.[^x] Two.[^y] Again.[^x]\n\n[^x]: Note x,\n    continued.\n[^y]: Note y.\n"),
            _src(tmp, "b", 2, "Also.[^1]\n\n[^1]: B's first note.\n"),
            _src(tmp, "c", 3, "Second volume.[^1]\n\n[^1]: C's note.\n"),
            _src(tmp, "d", 4, "Apparatus.[^own]\n\n[^own]: Prints in place.\n"),
        ],
        "volumes": [{"id": "i", "title": "Volume I"}, {"id": "ii", "title": "Volume II", "before_source_uid": "c"},
                    {"id": "iii", "title": "Volume III", "before_source_uid": "d"}],
    }


def test_harvest_numbers_per_volume_and_keeps_same_ids_in_different_sources_apart(tmp_path):
    work = _work(tmp_path)
    marks, notes = harvest_volume(work["sources"][:2])
    assert marks == {"a": {"x": 1, "y": 2}, "b": {"1": 3}}
    assert notes == [(1, "Note x, continued."), (2, "Note y."), (3, "B's first note.")]


def test_rewrite_sets_marks_and_drops_definitions():
    body, n = rewrite_markers("A.[^x] B.[^z]\n\n[^x]: gone\n    also gone\nkept\n", {"x": 4})
    assert n == 1
    assert "`\\OFEndnoteMark{4}`{=latex}" in body and "[^z]" in body
    assert "gone" not in body and "kept" in body


def test_split_puts_every_volumes_notes_in_the_sink(tmp_path):
    parts = split_manifest(_work(tmp_path, intro="Read these last."), generated_dir=tmp_path / "gen")
    one, two, three = parts
    assert one["volume"]["endnotes"]["marks"] == {"a": {"x": 1, "y": 2}, "b": {"1": 3}}
    assert two["volume"]["endnotes"]["marks"] == {"c": {"1": 1}}
    assert [s["uid"] for s in three["sources"]] == ["d", "work-endnotes"]
    notes = Path(three["sources"][1]["path"]).read_text(encoding="utf-8")
    assert "# Notes\n\nRead these last." in notes
    assert "## Notes to Volume I\n\n1. Note x, continued.\n\n2. Note y.\n\n3. B's first note." in notes
    assert "## Notes to Volume II\n\n1. C's note." in notes
    assert "Prints in place" not in notes  # the sink's own notes stay where they are
    assert three["volume"]["endnotes"]["count"] == 4


def test_unknown_sink_is_refused(tmp_path):
    work = _work(tmp_path)
    work["render"]["endnotes"]["sink"] = "iv"
    with pytest.raises(VolumeError, match="sink"):
        split_manifest(work, generated_dir=tmp_path / "gen")


def test_compiler_sets_marks_in_carrying_volumes(tmp_path):
    parts = split_manifest(_work(tmp_path), generated_dir=tmp_path / "gen")
    compiler = CompositeBundleCompiler()
    assert compiler.validate(parts[0]) == []
    plan = compiler.compile(parts[0])
    text = plan.render_source.read_text()
    assert "\\OFEndnoteMark{1}" in text and "\\OFEndnoteMark{3}" in text
    assert "Note x" not in text and "[^x]" not in text
    assert plan.boundary_assertions["endnotes"]["marks_set"] == {"a": 3, "b": 1}
    assert compiler.validate(parts[2]) == []
