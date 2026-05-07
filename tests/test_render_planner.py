"""Tests for the RenderPlanner seam between manifests and profiles."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.render_planner import plan_document_render, plan_manifest_render

GF = Path(__file__).resolve().parents[1]
SRC = GF / "fixtures" / "sources"


def test_document_render_plan_has_no_manifest_assembly():
    plan = plan_document_render(SRC / "source-001.md", profile_id="tech")

    assert plan.kind == "document"
    assert plan.manifest is None
    assert plan.assembly is None
    assert len(plan.children) == 1
    assert plan.children[0].resolved_profile.profile_family == "document_spine"
    assert plan.children[0].resolved_profile.canonical_profile_id == "yugen_tech"


def test_manifest_render_plan_has_manifest_family_and_child_profiles():
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": "planner-test",
        "profile": "generic-report",
        "render": {"assembly_strategy": "combined_markdown"},
        "sources": [
            {"uid": "intro", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1, "profile_id": "tech"},
            {"uid": "letter", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2, "profile_id": "mythic-letter"},
        ],
    }

    plan = plan_manifest_render(manifest)

    assert plan.kind == "manifest"
    assert plan.manifest.manifest_family == "bundle_longform"
    assert plan.assembly.strategy == "combined_markdown"
    assert [child.resolved_profile.profile_family for child in plan.children] == ["document_spine", "stationery_art"]
    assert [child.resolved_profile.canonical_profile_id for child in plan.children] == ["yugen_tech", "mythic-letter"]


def test_profile_family_request_defaults_to_neutral_document_spine_profile():
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": "planner-family-test",
        "sources": [
            {"uid": "spine", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1, "profile_family": "document_spine"},
        ],
    }

    plan = plan_manifest_render(manifest)

    assert plan.children[0].requested_profile_id is None
    assert plan.children[0].requested_profile_family == "document_spine"
    assert plan.children[0].resolved_profile.canonical_profile_id == "document-spine"
    assert [p.name for p in plan.children[0].resolved_profile.defaults_stack] == ["document_spine.yaml"]
