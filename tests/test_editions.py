"""C1/C2 — editions any profile can declare, in its own marker namespace."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine import source_preparation
from engine.editions import CodexEditionRenderError, preprocess_codex_edition_blocks
from engine.markers import MarkerError, edition_marker_re, line_marker_re, prefix_of
from engine.profile_resolver import resolve_profile
from engine.projection_plan import ProjectionPlan

DOC = """---
edition: client
---

Shared opening.

<!-- rp:variant id="pricing" guard="public" -->
Internal pricing: cost plus 12%.
<!-- rp:edition client -->
Pricing as quoted.
<!-- rp:edition public -->
<!-- rp:endvariant -->

Shared close.
"""


def test_prefix_rules():
    assert prefix_of(None) == "cx0" and prefix_of({"prefix": "rp"}) == "rp"
    with pytest.raises(MarkerError):
        prefix_of({"prefix": "Bad Prefix"})
    assert line_marker_re("rp").match("<!-- rp:breath -->").group(1) == "breath"
    assert not edition_marker_re("rp").search("<!-- cx0:variant id='a' -->")


def test_another_namespace_selects_and_guards(tmp_path):
    src = tmp_path / "s.md"
    src.write_text(DOC, encoding="utf-8")
    labels = ("internal", "client", "public")
    for edition, present, absent in (("client", "as quoted", "cost plus"), ("internal", "cost plus", "as quoted")):
        out = preprocess_codex_edition_blocks(src, tmp_path / edition, "r", edition, prefix="rp", labels=labels)
        text = out.rewritten_source.read_text()
        assert present in text and absent not in text and "rp:" not in text
    pub = preprocess_codex_edition_blocks(src, tmp_path / "p", "r", "public", prefix="rp", labels=labels)
    assert "cost plus" not in pub.rewritten_source.read_text()  # an empty override: removed for the public
    with pytest.raises(CodexEditionRenderError, match="not one this profile declares"):
        preprocess_codex_edition_blocks(src, tmp_path / "x", "r", "board", prefix="rp", labels=labels)
    with pytest.raises(CodexEditionRenderError, match="rp:edition labels"):
        preprocess_codex_edition_blocks(src, tmp_path / "y", "r", "client", prefix="rp", labels=("internal", "client"))


def test_a_package_profile_declares_editions_and_its_namespace(tmp_path, monkeypatch):
    repo = tmp_path / "profiles"
    (repo / "report-ed").mkdir(parents=True)
    (repo / "report-ed" / "profile.yaml").write_text(yaml.safe_dump({
        "schema_version": "profile_package_v1", "id": "report-ed", "extends": "document-spine",
        "markers": {"prefix": "rp"}, "editions": {"labels": ["internal", "client", "public"]},
    }), encoding="utf-8")
    monkeypatch.setenv("OF_PROFILE_PATH", str(repo))
    profile = resolve_profile("report-ed")
    assert profile.markers == {"prefix": "rp"} and profile.editions["labels"] == ("internal", "client", "public")
    src = tmp_path / "s.md"
    src.write_text(DOC, encoding="utf-8")
    plan = ProjectionPlan(profile_id="report-ed", render_id="r", render_source=src)
    out = source_preparation.codex_edition(plan, tmp_path, profile)
    text = Path(out.render_source).read_text()
    assert "as quoted" in text and "cost plus" not in text
    assert out.boundary_assertions["codex_edition"] == "client"
    # The same source under a profile without editions is refused, whatever the namespace.
    with pytest.raises(CodexEditionRenderError, match="declares none"):
        source_preparation.codex_edition(ProjectionPlan(profile_id="document-spine", render_id="r", render_source=src),
                                         tmp_path, resolve_profile("document-spine"))


def test_codex0_declares_its_namespace_and_editions():
    p = resolve_profile("codex0")
    assert p.markers == {"prefix": "cx0"}
    assert p.editions["labels"] == ("archival", "johannah", "witness", "reader")


def test_a_bundle_manifest_picks_the_edition(tmp_path):
    from engine.manifest_compiler import CompositeBundleCompiler

    src = tmp_path / "s.md"
    src.write_text(DOC.split("---", 2)[2], encoding="utf-8")
    manifest = {"kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "ed-probe",
                "profile": "document-spine", "presentation": {"title": "E"}, "variables": {"edition": "public"},
                "sources": [{"uid": "s", "path": str(src), "role": "primary_anchor", "order": 1}]}
    plan = CompositeBundleCompiler().compile(manifest)
    assert "edition" in plan.boundary_assertions["accepted_manifest_variables"]
    assert "edition: public" in plan.render_source.read_text()
