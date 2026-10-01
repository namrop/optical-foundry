"""The template contract (architecture review 2026-10-01, candidate 1; ruling 01a0f8ba-4937)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.manifest_compiler import CompositeBundleCompiler
from engine.template_contract import READ_TIME_DEFINITIONS, contract_text
from renderers.pandoc_renderer import PandocRenderer

TEMPLATES = Path(__file__).resolve().parents[1] / "profiles" / "40_latex_import" / "templates"
CONTRACT_COMMANDS = (
    "OFIntentionalBlankPage", "OFEnsureRightPage", "OFSectionDividerBackground",
    "OFApplySectionDividerProfile", "OFBeginAppendices", "OFDivMarkerHideBegin",
    "OFDivMarkerHideEnd", "OFSetRunningDivision", "OFSetRunningTagline", "OFSetRunningFooter",
)


def test_contract_defines_every_command_once_and_only_with_providecommand():
    text = contract_text()
    for name in CONTRACT_COMMANDS:
        assert len(re.findall(r"\\providecommand\{\\" + name + r"\}", text)) == 1, name
    assert "\\newcommand" not in text


def test_no_template_copies_the_default_definitions():
    """A template defines a contract command only to restyle it (codex0 does, twice)."""
    defaults = {name: None for name in CONTRACT_COMMANDS}
    owners = {}
    for template in TEMPLATES.glob("*.tex"):
        for name in defaults:
            if re.search(r"\\(?:newcommand|providecommand|NewDocumentCommand)\{\\" + name + r"\}", template.read_text()):
                owners.setdefault(name, []).append(template.name)
    assert owners.get("OFEnsureRightPage") is None
    assert owners.get("OFBeginAppendices") is None
    assert owners.get("OFDivMarkerHideBegin") is None
    assert sorted(owners.get("OFIntentionalBlankPage", [])) == ["codex0.tex"]
    assert sorted(owners.get("OFSectionDividerBackground", [])) == ["codex0.tex"]


def test_read_time_definitions_no_longer_carry_the_marker_wrappers():
    joined = "\n".join(READ_TIME_DEFINITIONS)
    assert "OFDivMarkerHide" not in joined
    assert "\\providecommand{\\OFChapterOpener}" in joined


@pytest.mark.skipif(
    not (shutil.which("pandoc") and shutil.which("xelatex") and shutil.which("pdftotext")),
    reason="pandoc/xelatex/pdftotext missing",
)
@pytest.mark.parametrize("profile", ["short-story", "household-paper"])
def test_a_profile_without_divider_commands_can_render_a_divider_bundle(tmp_path, profile):
    """These templates define none of the contract; before 2026-10-01 a divider failed to compile."""
    source = tmp_path / "body.md"
    source.write_text("---\nuid: body\ntitle: Body\n---\n\n# Body\n\nText after the divider.\n", encoding="utf-8")
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": f"contract-{profile}",
        "profile": profile,
        "sources": [{"uid": "body", "path": str(source), "role": "primary_anchor", "order": 1, "include_frontmatter": "none", "suppress_frontmatter": True}],
        "section_dividers": [{"uid": "d", "before_source_order": 1, "title": "Part One", "blank_after": True}],
        "render": {"include_toc": False, "numbersections": False},
    }
    plan = CompositeBundleCompiler().compile(manifest)
    evidence = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"))
    assert evidence["status"] == "ok", evidence.get("error")
    text = subprocess.run(["pdftotext", evidence["output"]["pdf_path"], "-"], capture_output=True, text=True).stdout
    assert "Part One" in text and "[[OFDIV:" not in text
