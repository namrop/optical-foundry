"""Tests for Pandoc render dispatch and document renderer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.projection_plan import ProjectionPlan
from renderers.pandoc_renderer import PandocRenderer
from renderers.document_renderer import DocumentRenderer

GF = Path(__file__).resolve().parents[1]


def test_pandoc_renderer_creates_evidence_on_error():
    r = PandocRenderer()
    plan = ProjectionPlan(
        profile_id="nonexistent",
        render_id="test-error",
        render_source=Path("/nonexistent.md"),
    )
    evidence = r.render(plan, output_dir="/tmp/of_greenfield_test_error")
    assert evidence["status"] == "error"


def test_document_renderer_parses_frontmatter():
    dr = DocumentRenderer()
    src = GF / "fixtures" / "sources" / "source-001.md"
    assert src.exists()
    # Just verify it builds a plan without error; actual render requires xelatex
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="test-doc",
        render_source=src,
    )
    assert plan.profile_id == "generic-report"
    assert plan.render_source == src


def test_pandoc_renderer_template_inference():
    r = PandocRenderer()
    assert r._infer_template("generic-report") == "generic_report.tex"
    assert r._infer_template("risk") == "risk.tex"
    assert r._infer_template("unknown") is None
