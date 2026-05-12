"""Tests for Graphviz/DOT generated-figure preprocessing."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.graphviz import (
    GRAPHVIZ_RENDERER_NAME,
    GraphvizRenderError,
    preprocess_graphviz_blocks,
    resolve_graphviz_command,
    validate_and_theme_dot_source,
)


def _dot_source() -> str:
    return "digraph G {\n  Oasis -> Foundry;\n  Foundry -> Evidence;\n}\n"


def test_resolve_graphviz_command_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("GRAPHVIZ_DOT", "/opt/foundry/bin/dot")

    assert resolve_graphviz_command() == ["/opt/foundry/bin/dot"]


def test_resolve_graphviz_command_uses_local_pinned_tool_before_path(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
    local_dot = tmp_path / ".tools" / "graphviz" / "v14.1.5" / "dot"
    local_dot.parent.mkdir(parents=True)
    local_dot.write_text("#!/bin/sh\n")

    def fake_which(name: str):
        if name == "dot":
            return "/usr/local/bin/dot"
        return None

    monkeypatch.setattr("engine.graphviz.shutil.which", fake_which)
    monkeypatch.setattr("engine.graphviz.LOCAL_DOT_BINARY", local_dot)

    assert resolve_graphviz_command() == [str(local_dot)]


def test_resolve_graphviz_command_raises_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
    monkeypatch.setattr("engine.graphviz.shutil.which", lambda _name: None)
    monkeypatch.setattr("engine.graphviz.LOCAL_DOT_BINARY", tmp_path / "missing-dot")

    with pytest.raises(GraphvizRenderError, match="Graphviz dot unavailable"):
        resolve_graphviz_command()


def test_validate_and_theme_dot_source_rejects_remote_references_by_default():
    with pytest.raises(GraphvizRenderError, match="remote reference"):
        validate_and_theme_dot_source('digraph G { a [image="https://example.com/x.svg"]; }', profile_id="civic")


def test_validate_and_theme_dot_source_rejects_non_graph_source():
    with pytest.raises(GraphvizRenderError, match="must start with graph or digraph"):
        validate_and_theme_dot_source("A -> B;", profile_id="civic")


def test_validate_and_theme_dot_source_injects_bounded_default_attributes_without_removing_source():
    themed, evidence = validate_and_theme_dot_source(_dot_source(), profile_id="civic")

    assert "Oasis -> Foundry" in themed
    assert "graph [" in themed
    assert "node [" in themed
    assert "edge [" in themed
    assert evidence["normalized_source_sha256"]
    assert evidence["theme"]["palette"]
    assert evidence["renderer"]["name"] == GRAPHVIZ_RENDERER_NAME
    assert evidence["warnings"] == []


def test_preprocess_graphviz_blocks_rewrites_dot_fences_and_records_evidence(tmp_path):
    source = tmp_path / "dot_doc.md"
    source.write_text(
        "---\ntitle: DOT Doc\n---\n\n"
        "Before.\n\n"
        "```dot\n"
        + _dot_source()
        + "```\n\n"
        "After.\n"
    )

    def fake_renderer(source_text: str, output_path: Path, render_context: dict) -> None:
        output_path.write_text(f"<svg><title>{render_context['theme']['palette'][0]}</title></svg>")

    result = preprocess_graphviz_blocks(
        source,
        profile_id="civic",
        output_dir=tmp_path / "out",
        render_id="dot-doc",
        renderer=fake_renderer,
        output_format="svg",
    )

    rewritten = result.rewritten_source.read_text()
    assert "```dot" not in rewritten
    assert "![Graphviz diagram 1]" in rewritten
    assert result.figure_inventory[0]["kind"] == "graphviz_dot"
    assert result.figure_inventory[0]["output_format"] == "svg"
    assert result.figure_inventory[0]["renderer"]["name"] == GRAPHVIZ_RENDERER_NAME
    assert Path(result.figure_inventory[0]["dot_source_path"]).exists()
    assert Path(result.figure_inventory[0]["path"]).exists()
