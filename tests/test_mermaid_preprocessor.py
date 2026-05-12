"""Tests for Mermaid chart preprocessing and profile-derived chart themes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.manifest_compiler import CompositeBundleCompiler
from engine.mermaid import preprocess_mermaid_blocks, resolve_mermaid_command, resolve_profile_chart_theme

GF = Path(__file__).resolve().parents[1]
SRC = GF / "fixtures" / "sources"


def test_resolve_mermaid_command_uses_pinned_npx_fallback(monkeypatch):
    monkeypatch.delenv("MERMAID_CLI", raising=False)

    def fake_which(name: str):
        if name == "mmdc":
            return None
        if name == "npx":
            return "/usr/local/bin/npx"
        return None

    monkeypatch.setattr("engine.mermaid.shutil.which", fake_which)

    assert resolve_mermaid_command() == ["/usr/local/bin/npx", "-y", "@mermaid-js/mermaid-cli@11.14.0"]


def test_resolve_mermaid_command_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("MERMAID_CLI", "/opt/foundry/bin/mmdc")

    assert resolve_mermaid_command() == ["/opt/foundry/bin/mmdc"]


def _fake_renderer(source: str, output_path: Path, config: dict) -> None:
    output_path.write_text(
        f"<svg><title>{config['themeVariables']['primaryColor']}</title><desc>{source}</desc></svg>"
    )


def test_profile_chart_theme_prefers_cam_profile_colors_from_style_package():
    theme = resolve_profile_chart_theme("cam")

    assert theme["source"] == "profile"
    assert theme["palette"][0] == "#0A3870"
    assert theme["palette"][1] == "#D5972B"
    assert theme["themeVariables"]["primaryColor"] == "#0A3870"
    assert theme["themeVariables"]["primaryTextColor"] == "#FBFBFA"
    assert theme["themeVariables"]["xyChart"]["plotColorPalette"].startswith("#0A3870")
    assert theme["vega"]["range"]["category"][0] == "#0A3870"


def test_preprocess_mermaid_blocks_rewrites_fences_to_generated_figures(tmp_path):
    source = tmp_path / "chart_doc.md"
    source.write_text(
        "---\ntitle: Chart Doc\n---\n\n"
        "Before.\n\n"
        "```mermaid\n"
        "xychart\n"
        "    title \"Revenue\"\n"
        "    x-axis [Q1, Q2]\n"
        "    y-axis \"Revenue\" 0 --> 10\n"
        "    bar [3, 8]\n"
        "```\n\n"
        "After.\n"
    )

    result = preprocess_mermaid_blocks(
        source,
        profile_id="cam",
        output_dir=tmp_path / "out",
        render_id="chart-doc",
        renderer=_fake_renderer,
        output_format="svg",
    )

    rewritten = result.rewritten_source.read_text()
    assert "```mermaid" not in rewritten
    assert "![Mermaid chart 1]" in rewritten
    assert result.figure_inventory[0]["kind"] == "mermaid"
    assert result.figure_inventory[0]["theme"]["palette"][0] == "#0A3870"
    assert Path(result.figure_inventory[0]["path"]).exists()


def test_manifest_assembly_mermaid_blocks_are_preprocessable(tmp_path):
    mermaid_source = tmp_path / "source-with-mermaid.md"
    mermaid_source.write_text(
        "---\nuid: mermaid-src\ntitle: Mermaid Source\n---\n\n"
        "# Mermaid Source\n\n"
        "```mermaid\n"
        "pie showData\n"
        "    title Mix\n"
        "    \"A\" : 2\n"
        "    \"B\" : 3\n"
        "```\n"
    )
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": "bundle-mermaid",
        "profile": "cam",
        "sources": [
            {"uid": "mermaid-src", "path": str(mermaid_source), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "appendix", "order": 2},
        ],
        "render": {"include_toc": False},
    }
    plan = CompositeBundleCompiler().compile(manifest)

    result = preprocess_mermaid_blocks(
        plan.render_source,
        profile_id=plan.profile_id,
        output_dir=tmp_path / "out",
        render_id=plan.render_id,
        renderer=_fake_renderer,
        output_format="svg",
    )

    rewritten = result.rewritten_source.read_text()
    assert "pie showData" not in rewritten
    assert "![Mermaid chart 1]" in rewritten
    assert result.figure_inventory[0]["source_path"] == str(plan.render_source)
