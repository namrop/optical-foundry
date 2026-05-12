"""Tests for D2 architecture-diagram generated-figure preprocessing."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.d2 import (
    PINNED_D2_VERSION,
    D2RenderError,
    preprocess_d2_blocks,
    resolve_d2_command,
    validate_and_theme_d2_source,
)


def _d2_source() -> str:
    return "Oasis -> Optical Foundry\nOptical Foundry -> Evidence\n"


def test_resolve_d2_command_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("D2_CLI", "/opt/foundry/bin/d2")

    assert resolve_d2_command() == ["/opt/foundry/bin/d2"]


def test_resolve_d2_command_uses_local_pinned_tool_before_path(monkeypatch, tmp_path):
    monkeypatch.delenv("D2_CLI", raising=False)
    local_d2 = tmp_path / ".tools" / "bin" / "d2"
    local_d2.parent.mkdir(parents=True)
    local_d2.write_text("#!/bin/sh\n")

    def fake_which(name: str):
        if name == "d2":
            return "/usr/local/bin/d2"
        return None

    monkeypatch.setattr("engine.d2.shutil.which", fake_which)
    monkeypatch.setattr("engine.d2.LOCAL_D2_BINARY", local_d2)

    assert resolve_d2_command() == [str(local_d2)]


def test_resolve_d2_command_raises_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("D2_CLI", raising=False)
    monkeypatch.setattr("engine.d2.shutil.which", lambda _name: None)
    monkeypatch.setattr("engine.d2.LOCAL_D2_BINARY", tmp_path / "missing-d2")

    with pytest.raises(D2RenderError, match="D2 CLI unavailable"):
        resolve_d2_command()


def test_validate_and_theme_d2_source_rejects_remote_references_by_default():
    with pytest.raises(D2RenderError, match="remote reference"):
        validate_and_theme_d2_source("x.icon: https://example.com/icon.svg\n", profile_id="civic")


def test_validate_and_theme_d2_source_prepends_bounded_profile_vars_without_overwriting_source():
    themed, evidence = validate_and_theme_d2_source(_d2_source(), profile_id="civic")

    assert themed.endswith(_d2_source())
    assert "vars: {" in themed
    assert "d2-primary" in themed
    assert evidence["normalized_source_sha256"]
    assert evidence["theme"]["palette"]
    assert evidence["renderer"]["version"] == PINNED_D2_VERSION
    assert evidence["warnings"] == []


def test_preprocess_d2_blocks_rewrites_fences_and_records_evidence(tmp_path):
    source = tmp_path / "d2_doc.md"
    source.write_text(
        "---\ntitle: D2 Doc\n---\n\n"
        "Before.\n\n"
        "```d2\n"
        + _d2_source()
        + "```\n\n"
        "After.\n"
    )

    def fake_renderer(source_text: str, output_path: Path, render_context: dict) -> None:
        output_path.write_text(f"<svg><title>{render_context['theme']['palette'][0]}</title></svg>")

    result = preprocess_d2_blocks(
        source,
        profile_id="civic",
        output_dir=tmp_path / "out",
        render_id="d2-doc",
        renderer=fake_renderer,
        output_format="svg",
    )

    rewritten = result.rewritten_source.read_text()
    assert "```d2" not in rewritten
    assert "![D2 diagram 1]" in rewritten
    assert result.figure_inventory[0]["kind"] == "d2"
    assert result.figure_inventory[0]["output_format"] == "svg"
    assert result.figure_inventory[0]["renderer"]["version"] == PINNED_D2_VERSION
    assert Path(result.figure_inventory[0]["source_path"]).exists()
    assert Path(result.figure_inventory[0]["path"]).exists()
