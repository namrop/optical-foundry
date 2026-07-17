"""Tests for full Vega generated-figure preprocessing."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.vega import (
    PINNED_VEGA_CLI_PACKAGE,
    VegaRenderError,
    preprocess_vega_blocks,
    resolve_vega_command,
    validate_and_theme_vega_spec,
)


def _bar_spec() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega/v5.json",
        "description": "Full Vega smoke bar chart",
        "width": 240,
        "height": 120,
        "padding": 5,
        "data": [{"name": "table", "values": [{"x": "A", "y": 3}, {"x": "B", "y": 7}]}],
        "scales": [
            {"name": "xscale", "type": "band", "domain": {"data": "table", "field": "x"}, "range": "width", "padding": 0.1},
            {"name": "yscale", "domain": {"data": "table", "field": "y"}, "nice": True, "range": "height"},
        ],
        "axes": [{"orient": "bottom", "scale": "xscale"}, {"orient": "left", "scale": "yscale"}],
        "marks": [
            {
                "type": "rect",
                "from": {"data": "table"},
                "encode": {
                    "enter": {
                        "x": {"scale": "xscale", "field": "x"},
                        "width": {"scale": "xscale", "band": 1},
                        "y": {"scale": "yscale", "field": "y"},
                        "y2": {"scale": "yscale", "value": 0},
                        "fill": {"value": "#0A3870"},
                    }
                },
            }
        ],
    }


def test_resolve_vega_command_uses_pinned_npx_package(monkeypatch):
    monkeypatch.delenv("VEGA_CLI", raising=False)

    def fake_which(name: str):
        if name in {"vg2svg", "vg2pdf"}:
            return None
        if name == "npx":
            return "/usr/local/bin/npx"
        return None

    monkeypatch.setattr("engine.vega.shutil.which", fake_which)

    assert resolve_vega_command("pdf") == ["/usr/local/bin/npx", "-y", "-p", PINNED_VEGA_CLI_PACKAGE, "vg2pdf"]
    assert resolve_vega_command("svg") == ["/usr/local/bin/npx", "-y", "-p", PINNED_VEGA_CLI_PACKAGE, "vg2svg"]


def test_validate_and_theme_vega_spec_injects_profile_palette_without_overriding_author_values():
    spec = _bar_spec()
    spec["background"] = "#ABCDEF"
    themed, evidence = validate_and_theme_vega_spec(spec, profile_id="cam")

    assert themed["background"] == "#ABCDEF"
    assert themed["config"]["range"]["category"][0] == "#0A3870"
    assert themed["config"]["axis"]["labelColor"] == evidence["theme"]["tokens"]["secondary"]
    assert evidence["normalized_spec_sha256"]
    assert evidence["theme"]["palette"][0] == "#0A3870"
    assert evidence["warnings"] == []


def test_validate_vega_spec_rejects_remote_data_url_by_default():
    spec = _bar_spec()
    spec["data"] = [{"name": "remote", "url": "https://example.com/data.json"}]

    with pytest.raises(VegaRenderError, match="remote data URL"):
        validate_and_theme_vega_spec(spec, profile_id="cam")


def test_validate_vega_spec_warns_on_expression_bearing_fields():
    spec = _bar_spec()
    spec["signals"] = [{"name": "danger", "update": "datum.value"}]
    themed, evidence = validate_and_theme_vega_spec(spec, profile_id="cam")

    assert themed["signals"][0]["name"] == "danger"
    assert any("expression-bearing" in warning for warning in evidence["warnings"])


def test_preprocess_vega_blocks_rewrites_fences_and_records_evidence(tmp_path):
    source = tmp_path / "vega_doc.md"
    source.write_text(
        "---\ntitle: Vega Doc\n---\n\n"
        "Before.\n\n"
        "```vega\n"
        + json.dumps(_bar_spec(), indent=2)
        + "\n```\n\n"
        "After.\n"
    )

    def fake_renderer(spec: dict, output_path: Path, render_context: dict) -> None:
        output_path.write_text(f"<svg><title>{spec['config']['range']['category'][0]}</title></svg>")

    result = preprocess_vega_blocks(
        source,
        profile_id="cam",
        output_dir=tmp_path / "out",
        render_id="vega-doc",
        renderer=fake_renderer,
        output_format="svg",
    )

    rewritten = result.rewritten_source.read_text()
    assert "```vega" not in rewritten
    # No invented "Vega chart N" caption/alt. For non-PDF output the image
    # carries the spec description as alt text; the figure id is retained.
    assert "Vega chart" not in rewritten
    assert "![Full Vega smoke bar chart]" in rewritten
    assert "{#fig:vega-1}" in rewritten
    assert result.figure_inventory[0]["kind"] == "vega"
    assert result.figure_inventory[0]["output_format"] == "svg"
    assert result.figure_inventory[0]["alt"] == "Full Vega smoke bar chart"
    assert result.figure_inventory[0]["caption"] == ""
    assert result.figure_inventory[0]["theme"]["palette"][0] == "#0A3870"
    assert result.figure_inventory[0]["normalized_spec_sha256"]
    assert Path(result.figure_inventory[0]["path"]).exists()


def test_preprocess_vega_pdf_no_caption_emits_raw_includegraphics(tmp_path):
    """A caption-less PDF figure must not become an implicit captioned figure."""
    source = tmp_path / "vega_doc.md"
    source.write_text("```vega\n" + json.dumps(_bar_spec()) + "\n```\n")

    def fake_renderer(spec, output_path, render_context):
        output_path.write_text("%PDF-1.5 fake")

    result = preprocess_vega_blocks(
        source, profile_id="cam", output_dir=tmp_path / "out",
        render_id="doc", renderer=fake_renderer, output_format="pdf",
    )
    rewritten = result.rewritten_source.read_text()
    assert "Vega chart" not in rewritten
    assert "\\caption" not in rewritten  # no caption, no figure environment
    assert "\\begin{center}\\includegraphics" in rewritten
    assert "```{=latex}" in rewritten
    assert result.figure_inventory[0]["caption"] == ""


def test_preprocess_vega_pdf_authored_caption_numbered(tmp_path):
    """An authored caption renders a numbered figure; description stays alt."""
    source = tmp_path / "vega_doc.md"
    source.write_text(
        '```vega {#fig-x caption="Finding profile" numbered=true}\n'
        + json.dumps(_bar_spec()) + "\n```\n"
    )

    def fake_renderer(spec, output_path, render_context):
        output_path.write_text("%PDF-1.5 fake")

    result = preprocess_vega_blocks(
        source, profile_id="cam", output_dir=tmp_path / "out",
        render_id="doc", renderer=fake_renderer, output_format="pdf",
        figure_captions=False, figure_numbering=False,
    )
    rewritten = result.rewritten_source.read_text()
    assert "\\begin{figure}" in rewritten
    assert "\\caption{Finding profile}" in rewritten  # numbered => \caption (not \caption*)
    assert "\\label{fig-x}" in rewritten
    assert result.figure_inventory[0]["caption"] == "Finding profile"
    assert result.figure_inventory[0]["numbered"] is True


def test_preprocess_vega_pdf_caption_unnumbered_uses_starred_caption(tmp_path):
    source = tmp_path / "vega_doc.md"
    source.write_text(
        '```vega {caption="Finding profile" numbered=false}\n'
        + json.dumps(_bar_spec()) + "\n```\n"
    )

    def fake_renderer(spec, output_path, render_context):
        output_path.write_text("%PDF-1.5 fake")

    result = preprocess_vega_blocks(
        source, profile_id="cam", output_dir=tmp_path / "out",
        render_id="doc", renderer=fake_renderer, output_format="pdf",
        figure_numbering=True,  # per-figure numbered=false overrides doc default
    )
    rewritten = result.rewritten_source.read_text()
    assert "\\caption*{Finding profile}" in rewritten
    assert result.figure_inventory[0]["numbered"] is False


def test_preprocess_vega_blocks_preserves_heading_after_fence(tmp_path):
    source = tmp_path / "vega_doc.md"
    source.write_text(
        "---\ntitle: Vega Doc\n---\n\n"
        "```vega\n"
        + json.dumps(_bar_spec(), indent=2)
        + "\n```\n"
        "### Key Takeaways\n\n"
        "Body.\n"
    )

    def fake_renderer(spec: dict, output_path: Path, render_context: dict) -> None:
        output_path.write_text("<svg></svg>")

    result = preprocess_vega_blocks(
        source,
        profile_id="cam",
        output_dir=tmp_path / "out",
        render_id="vega-doc",
        renderer=fake_renderer,
        output_format="svg",
    )

    rewritten = result.rewritten_source.read_text()
    assert "{#fig:vega-1}\n\n### Key Takeaways" in rewritten
