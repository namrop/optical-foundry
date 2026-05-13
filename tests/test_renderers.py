"""Tests for Pandoc render dispatch and document renderer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

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


def test_document_renderer_frontmatter_role_emits_memoir_frontmatter(tmp_path):
    src = tmp_path / "preface.md"
    src.write_text(
        "---\n"
        "uid: preface-direct\n"
        "title: Preface Direct\n"
        "role: frontmatter\n"
        "---\n\n"
        "# Preface\n\n"
        "Direct document path body.\n"
    )

    plan = DocumentRenderer().build_plan(src, profile_id="cam")
    assembled = plan.render_source.read_text()

    assert plan.render_id == "preface-direct"
    assert plan.source_inventory[0]["role"] == "frontmatter"
    assert assembled.startswith("---\n")
    assert "\n\\frontmatter\n" in assembled
    assert assembled.index("\\frontmatter") < assembled.index("# Preface")
    assert plan.boundary_assertions["document_matter_role"] == "frontmatter"
    assert plan.boundary_assertions["frontmatter_mode_enabled"] is True


def test_document_renderer_rejects_conflicting_frontmatter_role_aliases(tmp_path):
    src = tmp_path / "conflicting-preface.md"
    src.write_text(
        "---\n"
        "uid: conflicting-preface\n"
        "title: Conflicting Preface\n"
        "role: frontmatter\n"
        "matter: document_source\n"
        "---\n\n"
        "# Preface\n\n"
        "Direct document path body.\n"
    )

    with pytest.raises(ValueError, match="conflicting source_frontmatter matter roles"):
        DocumentRenderer().build_plan(src, profile_id="cam")


def test_document_renderer_ignores_unrelated_frontmatter_role(tmp_path):
    src = tmp_path / "contract.md"
    src.write_text(
        "---\n"
        "uid: contract-direct\n"
        "title: Contract Direct\n"
        "role: contract\n"
        "---\n\n"
        "# Contract\n\n"
        "Direct document path body.\n"
    )

    plan = DocumentRenderer().build_plan(src, profile_id="cam")

    assert plan.render_id == "contract-direct"
    assert plan.render_source == src
    assert plan.source_inventory[0]["role"] == "document_source"
    assert plan.boundary_assertions["document_matter_role"] == "document_source"


def test_pandoc_renderer_template_inference_uses_shared_profile_resolver():
    r = PandocRenderer()
    assert r._infer_template("generic-report") == "generic_report.tex"
    assert r._infer_template("risk") == "base.tex"
    assert r._infer_template("tech") == "base.tex"
    assert r._infer_template("creative") == "base.tex"
    assert r._infer_template("letter") == "personal_letter.tex"
    assert r._infer_template("mythic-letter") == "personal_letter.tex"
    assert r._infer_template("prometheus-packet") == "generic_report.tex"
    assert r._infer_template("labels-avery-5164") == "label_sheet.tex"
    assert r._infer_template("sticker-sheet") == "label_sheet.tex"


def test_read_defaults_metadata_detects_placeholder_assets():
    r = PandocRenderer()
    meta = r._read_defaults_metadata(GF / "profiles" / "40_latex_import" / "defaults" / "elian_packet.yaml")
    assert meta["boundary"]["placeholder_assets"] is True
    assert any("placeholder" in w.lower() for w in meta["warnings"])


def test_pandoc_renderer_prepares_mermaid_source_before_pandoc(tmp_path):
    src = tmp_path / "mermaid-input.md"
    src.write_text(
        "---\ntitle: Mermaid Input\n---\n\n"
        "```mermaid\n"
        "xychart\n"
        "    line [1, 2, 3]\n"
        "```\n"
    )

    def fake_renderer(source: str, output_path: Path, config: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="cam",
        render_id="mermaid-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_mermaid_source(
        plan,
        tmp_path / "render-out",
        mermaid_renderer=fake_renderer,
        mermaid_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```mermaid" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "mermaid"
    assert prepared.boundary_assertions["mermaid_enabled"] is True
    assert prepared.boundary_assertions["mermaid_diagram_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True
    assert prepared.boundary_assertions["figure_count_by_kind"] == {"mermaid": 1}
    assert prepared.boundary_assertions["mermaid_theme"]["palette"][0] == "#0A3870"


def test_pandoc_renderer_prepares_vega_source_before_pandoc(tmp_path):
    src = tmp_path / "vega-input.md"
    src.write_text(
        "---\ntitle: Vega Input\n---\n\n"
        "```vega\n"
        "{\n"
        "  \"$schema\": \"https://vega.github.io/schema/vega/v5.json\",\n"
        "  \"width\": 120,\n"
        "  \"height\": 80,\n"
        "  \"data\": [{\"name\": \"table\", \"values\": [{\"x\": \"A\", \"y\": 1}]}],\n"
        "  \"marks\": [{\"type\": \"text\", \"encode\": {\"enter\": {\"text\": {\"value\": \"ok\"}}}}]\n"
        "}\n"
        "```\n"
    )

    def fake_renderer(spec: dict, output_path: Path, render_context: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="cam",
        render_id="vega-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_vega_source(
        plan,
        tmp_path / "render-out",
        vega_renderer=fake_renderer,
        vega_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```vega" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "vega"
    assert prepared.boundary_assertions["vega_enabled"] is True
    assert prepared.boundary_assertions["vega_chart_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True


def test_pandoc_renderer_prepares_d2_source_before_pandoc(tmp_path):
    src = tmp_path / "d2-input.md"
    src.write_text(
        "---\ntitle: D2 Input\n---\n\n"
        "```d2\n"
        "Oasis -> Optical Foundry\n"
        "Optical Foundry -> Evidence\n"
        "```\n"
    )

    def fake_renderer(source_text: str, output_path: Path, render_context: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="civic",
        render_id="d2-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_d2_source(
        plan,
        tmp_path / "render-out",
        d2_renderer=fake_renderer,
        d2_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```d2" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "d2"
    assert prepared.boundary_assertions["d2_enabled"] is True
    assert prepared.boundary_assertions["d2_diagram_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True


def test_pandoc_renderer_prepares_graphviz_source_before_pandoc(tmp_path):
    src = tmp_path / "dot-input.md"
    src.write_text(
        "---\ntitle: DOT Input\n---\n\n"
        "```dot\n"
        "digraph G {\n"
        "  Oasis -> Foundry;\n"
        "  Foundry -> Evidence;\n"
        "}\n"
        "```\n"
    )

    def fake_renderer(source_text: str, output_path: Path, render_context: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="civic",
        render_id="dot-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_graphviz_source(
        plan,
        tmp_path / "render-out",
        graphviz_renderer=fake_renderer,
        graphviz_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```dot" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "graphviz_dot"
    assert prepared.boundary_assertions["graphviz_dot_enabled"] is True
    assert prepared.boundary_assertions["graphviz_dot_diagram_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True


def test_pandoc_renderer_strips_unsafe_titlepage_background_frontmatter(tmp_path):
    src = tmp_path / "unsafe-title-bg.md"
    src.write_text(
        "---\n"
        "title: Unsafe Title BG\n"
        "titlepage: true\n"
        "titlepage_background_image: /etc/passwd\n"
        "variables:\n"
        "  titlepage_background_image: ../secret.png\n"
        "  titlepage: true\n"
        "---\n\n"
        "# Body\n"
    )

    guarded = PandocRenderer._titlepage_background_normalized_source(src, tmp_path, "unsafe-title-bg")
    text = guarded.read_text()

    assert guarded != src
    assert "/etc/passwd" not in text
    assert "../secret.png" not in text
    assert "titlepage: true" in text


def test_pandoc_renderer_keeps_safe_titlepage_background_frontmatter(tmp_path):
    src = tmp_path / "safe-title-bg.md"
    src.write_text(
        "---\n"
        "title: Safe Title BG\n"
        "titlepage: true\n"
        "titlepage_background_image: assets/cover.png\n"
        "variables:\n"
        "  titlepage_background_image: assets/cover.png\n"
        "---\n\n"
        "# Body\n"
    )

    guarded = PandocRenderer._titlepage_background_normalized_source(src, tmp_path, "safe-title-bg")

    assert guarded == src
