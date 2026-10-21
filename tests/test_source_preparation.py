"""Source preparation (architecture review candidate 3; keeper ruling 01a0f930-407c)."""
from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest

from engine import profile_resolver, source_preparation
from engine.profile_resolver import resolve_profile
from engine.projection_plan import ProjectionPlan
from renderers.document_renderer import DocumentRenderer
from renderers.pandoc_renderer import PandocRenderer


def _plan(tmp_path: Path, body: str, profile: str = "document-spine") -> ProjectionPlan:
    src = tmp_path / "doc.md"
    src.write_text(f"---\ntitle: Doc\ntitlepage_background_image: ../escape.png\n---\n\n{body}\n", encoding="utf-8")
    return ProjectionPlan(profile_id=profile, render_id="doc", render_source=src,
                          output_format="pdf", output_extension=".pdf")


def test_the_steps_and_their_order():
    assert source_preparation.STEPS == (
        "codex_edition", "endnotes", "layout_images", "mermaid", "vega", "d2", "graphviz", "emoji",
        "stationery_opening", "titlepage_background_guard", "resource_pinning",
    )


def test_a_profile_that_declares_nothing_gets_every_step(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    prepared = source_preparation.prepare(_plan(tmp_path, "A candle 🕯 here."), resolve_profile("document-spine"), out)
    assert prepared.record["declared_by"] == "default"
    ran = {s["step"]: s for s in prepared.record["steps"]}
    assert [s["step"] for s in prepared.record["steps"]] == list(source_preparation.STEPS)
    assert all(s["ran"] for s in ran.values())
    assert ran["emoji"]["changed"] and ran["titlepage_background_guard"]["changed"]
    assert not ran["mermaid"]["changed"]
    assert "OFEmoji" in prepared.source.read_text(encoding="utf-8")
    assert "escape.png" not in prepared.source.read_text(encoding="utf-8")


def test_a_profile_runs_only_the_steps_it_declares(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    profile = dataclasses.replace(resolve_profile("document-spine"), source_preparation=("titlepage_background_guard",))
    plan = _plan(tmp_path, "A candle 🕯 here.")
    prepared = source_preparation.prepare(plan, profile, out)
    assert prepared.record["declared_by"] == "profile"
    ran = {s["step"]: s["ran"] for s in prepared.record["steps"]}
    assert ran == {step: step == "titlepage_background_guard" for step in source_preparation.STEPS}
    text = prepared.source.read_text(encoding="utf-8")
    assert "🕯" in text and "OFEmoji" not in text          # emoji not declared: left as written
    assert "escape.png" not in text                         # the declared guard ran
    assert prepared.plan.render_source == plan.render_source


def test_declarations_are_validated_when_the_profile_resolves(monkeypatch):
    assert source_preparation.validate_declaration(["emoji"]) == []
    assert "unknown step" in source_preparation.validate_declaration(["emojis"])[0]
    spec = dict(profile_resolver.PROFILE_SPECS["document-spine"], source_preparation=["emojis"])
    monkeypatch.setitem(profile_resolver.PROFILE_SPECS, "document-spine", spec)
    with pytest.raises(ValueError, match="unknown step"):
        resolve_profile("document-spine")
    monkeypatch.setitem(profile_resolver.PROFILE_SPECS, "document-spine", dict(spec, source_preparation=["emoji", "codex_edition"]))
    assert resolve_profile("document-spine").source_preparation == ("emoji", "codex_edition")


def test_no_profile_declares_steps_yet():
    """The ruling lets a profile declare; it chose none, so every render keeps every step."""
    assert [p for p, spec in profile_resolver.PROFILE_SPECS.items() if "source_preparation" in spec] == []


def test_the_renderer_no_longer_carries_the_steps():
    for name in ("_prepare_codex_edition_source", "_prepare_layout_image_source", "_prepare_mermaid_source",
                 "_prepare_emoji_substitution_source", "_stationery_normalized_source",
                 "_titlepage_background_normalized_source", "_pinned_resource_source"):
        assert not hasattr(PandocRenderer, name), name


@pytest.mark.skipif(not (shutil.which("pandoc") and shutil.which("xelatex")), reason="pandoc/xelatex missing")
def test_render_evidence_records_each_step(tmp_path):
    src = tmp_path / "s.md"
    src.write_text("---\ntitle: S\ntoc: false\nnumbersections: false\n---\n\nPlain text.\n", encoding="utf-8")
    plan = DocumentRenderer().build_plan(src, "generic-report")
    evidence = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"), draft=True)
    assert evidence["status"] == "ok", evidence.get("error")
    record = evidence["render_metadata"]["source_preparation"]
    assert record["declared_by"] == "default"
    assert [s["step"] for s in record["steps"]] == list(source_preparation.STEPS)
