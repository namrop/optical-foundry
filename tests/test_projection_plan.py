"""Tests for engine.projection_plan — ProjectionPlan and AssemblyView."""
from pathlib import Path
from engine.projection_plan import ProjectionPlan, AssemblyView


def test_plan_minimal():
    plan = ProjectionPlan(profile_id="risk", render_id="test-001", render_source=Path("/tmp/source.md"))
    assert plan.profile_id == "risk"
    assert plan.render_id == "test-001"
    assert not plan.has_assembly


def test_plan_with_assembly():
    av = AssemblyView(
        assembly_kind="composite_bundle",
        source_order=["a", "b"],
        source_paths={"a": "/tmp/a.md", "b": "/tmp/b.md"},
        source_roles={"a": "primary", "b": "supporting"},
    )
    plan = ProjectionPlan(profile_id="cam", render_id="test-002", render_source=Path("/tmp/bundle.md"), assembly=av)
    assert plan.has_assembly
    assert plan.assembly is not None
    assert plan.assembly.assembly_kind == "composite_bundle"


def test_plan_defaults_unchanged():
    plan = ProjectionPlan(profile_id="risk", render_id="t", render_source=Path("/tmp/s.md"))
    assert plan.page_size == "letter"
    assert plan.output_format == "pdf"
    assert plan.toc is True
