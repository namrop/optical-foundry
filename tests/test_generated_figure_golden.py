"""Golden generated-figure pipeline test covering all supported figure lanes."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.projection_plan import ProjectionPlan
from renderers.pandoc_renderer import PandocRenderer


def test_generated_figure_golden_pipeline_rewrites_all_supported_fences(tmp_path):
    src = tmp_path / "golden-generated-figures.md"
    src.write_text(
        "---\n"
        "title: Golden Generated Figure Pipeline\n"
        "---\n\n"
        "# Golden generated figures\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "  A[Markdown] --> B[Mermaid]\n"
        "  B --> C[Evidence]\n"
        "```\n\n"
        "```vega\n"
        + json.dumps(
            {
                "$schema": "https://vega.github.io/schema/vega/v5.json",
                "width": 120,
                "height": 80,
                "data": [{"name": "table", "values": [{"x": "A", "y": 2}, {"x": "B", "y": 5}]}],
                "scales": [
                    {"name": "x", "type": "band", "domain": {"data": "table", "field": "x"}, "range": "width"},
                    {"name": "y", "type": "linear", "domain": {"data": "table", "field": "y"}, "range": "height"},
                ],
                "marks": [
                    {
                        "type": "rect",
                        "from": {"data": "table"},
                        "encode": {
                            "enter": {
                                "x": {"scale": "x", "field": "x"},
                                "width": {"scale": "x", "band": 0.8},
                                "y": {"scale": "y", "field": "y"},
                                "y2": {"scale": "y", "value": 0},
                            }
                        },
                    }
                ],
            }
        )
        + "\n```\n\n"
        "```d2\n"
        "Oasis -> Optical Foundry\n"
        "Optical Foundry -> Evidence\n"
        "```\n\n"
        "```dot\n"
        "digraph G {\n"
        "  Markdown -> Graphviz;\n"
        "  Graphviz -> Evidence;\n"
        "}\n"
        "```\n"
    )

    def fake_text_renderer(_source_text: str, output_path: Path, _context: dict) -> None:
        output_path.write_text("<svg></svg>")

    def fake_vega_renderer(_spec: dict, output_path: Path, _context: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="civic",
        render_id="golden-generated-figures",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    renderer = PandocRenderer()
    out_dir = tmp_path / "render-out"
    plan = renderer._prepare_mermaid_source(plan, out_dir, mermaid_renderer=fake_text_renderer, mermaid_output_format="svg")
    plan = renderer._prepare_vega_source(plan, out_dir, vega_renderer=fake_vega_renderer, vega_output_format="svg")
    plan = renderer._prepare_d2_source(plan, out_dir, d2_renderer=fake_text_renderer, d2_output_format="svg")
    plan = renderer._prepare_graphviz_source(plan, out_dir, graphviz_renderer=fake_text_renderer, graphviz_output_format="svg")

    rewritten = plan.render_source.read_text()
    assert "```mermaid" not in rewritten
    assert "```vega" not in rewritten
    assert "```d2" not in rewritten
    assert "```dot" not in rewritten
    assert [figure["kind"] for figure in plan.figure_inventory] == ["mermaid", "vega", "d2", "graphviz_dot"]
    assert plan.boundary_assertions["generated_figures_enabled"] is True
    assert plan.boundary_assertions["figure_count_by_kind"] == {
        "mermaid": 1,
        "vega": 1,
        "d2": 1,
        "graphviz_dot": 1,
    }
    assert plan.boundary_assertions["mermaid_enabled"] is True
    assert plan.boundary_assertions["vega_enabled"] is True
    assert plan.boundary_assertions["d2_enabled"] is True
    assert plan.boundary_assertions["graphviz_dot_enabled"] is True
