from pathlib import Path

import pytest

from engine.endnotes import EndnoteError
from engine.work_render import WorkVolume, _prepare_work_endnotes, work_manifest_errors


def volumes(tmp_path):
    body = tmp_path / "body.md"
    body.write_text('<!-- cx0:variant id="one" -->\nHidden.[^hidden]\n[^hidden]: Hidden note.\n<!-- cx0:edition reader -->\nVisible.[^shown]\n[^shown]: Visible note.\n<!-- cx0:endvariant -->\n')
    frame = tmp_path / "frame.md"
    frame.write_text('# Notes\n\nOur intro.\n\n<<ENDNOTES>>\n')
    def bundle(name, path):
        return {"kind": "codex_bundle", "schema_version": "bundle_manifest_v1",
                "bundle_id": name, "bundle_name": name, "profile": "codex0",
                "variables": {"codex_edition": "reader"},
                "sources": [{"uid": name, "path": str(path), "order": 1, "role": "primary_anchor", "include_frontmatter": "none"}],
                "render": {"include_toc": False, "suppress_source_wrapper_headings": True}}
    return [WorkVolume(bundle("reading", body), None, "one", 1, 2, "Volume I"),
            WorkVolume(bundle("sink", frame), None, "two", 2, 2, "Volume II")]


def test_work_notes_harvest_after_edition_and_preserve_frame(tmp_path):
    vols = volumes(tmp_path)
    _prepare_work_endnotes(vols, {"sink": "two", "replace_source_uid": "sink", "mark_mode": "native"}, tmp_path / "out")
    text = Path(vols[1].manifest["sources"][0]["path"]).read_text()
    assert text == '# Notes\n\nOur intro.\n\n## Notes to Volume I\n\n1. Visible note.\n'
    assert vols[0].manifest["volume"]["endnotes"]["count"] == 1
    assert "combined_marks" not in vols[0].manifest["volume"]["endnotes"]


def test_work_notes_default_engine_marks_use_resolved_ids(tmp_path):
    vols = volumes(tmp_path)
    _prepare_work_endnotes(vols, {"sink": "two"}, tmp_path / "out")
    assert vols[0].manifest["volume"]["endnotes"]["combined_marks"] == {"shown": 1}
    assert len(vols[1].manifest["sources"]) == 2


def test_work_notes_refuse_unknown_sink_and_missing_marker(tmp_path):
    vols = volumes(tmp_path)
    with pytest.raises(EndnoteError, match="not a volume id"):
        _prepare_work_endnotes(vols, {"sink": "no"}, tmp_path / "out")
    Path(vols[1].manifest["sources"][0]["path"]).write_text("No slot here.")
    with pytest.raises(EndnoteError, match="exactly one"):
        _prepare_work_endnotes(vols, {"sink": "two", "replace_source_uid": "sink"}, tmp_path / "out")


def test_work_notes_engine_marks_lower_after_edition(tmp_path, monkeypatch):
    from engine.work_render import _render_one
    from renderers.pandoc_renderer import PandocRenderer
    vols = volumes(tmp_path)
    vols[0].manifest["volume"] = {"id": "one", "number": 1, "count": 2}
    vols[1].manifest["volume"] = {"id": "two", "number": 2, "count": 2}
    _prepare_work_endnotes(vols, {"sink": "two"}, tmp_path / "harvest")
    captured = {}
    def render(self, plan, **kwargs):
        from engine import source_preparation
        from engine.profile_resolver import resolve_profile
        prepared = source_preparation.prepare(plan, resolve_profile("codex0"), Path(kwargs["output_dir"]))
        plan = prepared.plan
        captured["text"] = plan.render_source.read_text()
        captured["marks"] = plan.boundary_assertions["endnotes"]["marks_set"]
        return {"status": "ok"}
    monkeypatch.setattr(PandocRenderer, "render", render)
    _render_one(vols[0].manifest, None, tmp_path / "render")
    assert "\\OFEndnoteMark{1}" in captured["text"]
    assert "Hidden." not in captured["text"]
    assert "[^shown]" not in captured["text"]
    assert captured["marks"] == {"assembled": 1}


def test_work_schema_accepts_and_checks_endnotes():
    manifest = {"kind": "work", "schema_version": "work_manifest_v1", "work_id": "test-work",
                "volumes": [{"id": "one", "manifest": "one.yaml"}, {"id": "two", "manifest": "two.yaml"}],
                "render": {"endnotes": {"sink": "two", "mark_mode": "native", "replace_source_uid": "sink"}}}
    assert work_manifest_errors(manifest) == []
    manifest["render"]["endnotes"]["mark_mode"] = "guess"
    assert work_manifest_errors(manifest)
