"""Tests for the short-story profile: resolution, the source grammar lowered by
filters/short_story.lua, and one real render measured as a PDF.

The fixture story is synthetic placeholder text; no keeper writing appears here.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.profile_checker import check_profile  # noqa: E402
from engine.profile_resolver import resolve_profile  # noqa: E402

LOCAL_IMPORT = ROOT / "profiles" / "40_latex_import"
FILTER = LOCAL_IMPORT / "filters" / "short_story.lua"
SAMPLE = ROOT / "fixtures" / "sources" / "short_story_sample.md"
HALF_LETTER_PT = (396.0, 612.0)
TOLERANCE = 1.0


def _latex(markdown: str) -> str:
    """Run pandoc with the profile filter over `markdown`, returning LaTeX."""
    result = subprocess.run(
        [
            "pandoc",
            "-f",
            "markdown+footnotes+yaml_metadata_block+smart",
            "-t",
            "latex",
            "--lua-filter",
            str(FILTER),
        ],
        input=markdown,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# ── resolution ───────────────────────────────────────────────────────────────


def test_short_story_resolves_to_its_own_defaults_and_template():
    resolved = resolve_profile("short-story")
    assert [p.name for p in resolved.defaults_stack] == ["short_story.yaml"]
    assert resolved.template_path.name == "short_story.tex"
    assert resolved.template_path.exists()


def test_short_story_underscore_alias_resolves_to_same_profile():
    assert resolve_profile("short_story").template_path.name == "short_story.tex"


def test_short_story_is_registered_in_the_profile_checker():
    cap = check_profile("short-story")
    assert cap.defaults_found is not None
    assert cap.template_found is not None
    assert cap.bundle_compatibility != "unknown"
    assert "No known compatibility classification" not in " ".join(cap.bundle_reasons)


def test_short_story_fonts_are_foundry_local():
    fonts = resolve_profile("short-story").font_policy["fonts"]
    assert fonts, "profile declares no fonts"
    assert all(f["status"] == "foundry_local" for f in fonts), fonts


# ── source grammar ───────────────────────────────────────────────────────────


def test_first_paragraph_opens_with_a_drop_cap():
    tex = _latex("Some really strange things.\n\nSecond paragraph.\n")
    assert "\\noindent\\lettrine{S}{ome} really strange things." in tex
    assert "\\noindent Second" not in tex


def test_horizontal_rule_is_a_scene_break_and_the_next_paragraph_is_flush():
    tex = _latex("First.\n\nSecond.\n\n***\n\nAfter the break.\n\nIndented again.\n")
    assert "\\SSSceneBreak" in tex
    assert "\\rule" not in tex
    assert "\\noindent After the break." in tex
    assert "\\noindent Indented" not in tex


def test_dropcap_can_be_switched_off_from_frontmatter():
    tex = _latex("---\nss_dropcap: false\n---\n\nSome text.\n")
    assert "\\lettrine" not in tex
    assert "\\noindent Some text." in tex


def test_smart_quoted_opening_is_carried_as_ante_and_closed():
    tex = _latex('"You don\'t want to," she said.\n')
    # Pandoc's LaTeX writer spells the closing curly quote as '' and the
    # apostrophe as '; both typeset as the curly marks.
    assert "\\lettrine[ante=\u201c]{Y}{ou} don't want to,'' she said." in tex


def test_literal_curly_quote_opening_is_carried_as_ante():
    tex = _latex("\u201cYou don\u2019t,\u201d she said.\n")
    assert "\\lettrine[ante=\u201c]{Y}{ou}" in tex


def test_paragraph_opening_with_markup_falls_back_to_flush():
    tex = _latex("*Nobody* could say.\n")
    assert "\\lettrine" not in tex
    assert "\\noindent \\emph{Nobody}" in tex


# ── real render ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("short_story")
    result = subprocess.run(
        [sys.executable, "-m", "cli", "doc", str(SAMPLE.relative_to(ROOT)),
         "--profile", "short-story", "--output", str(out)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    pdf = out / "short_story_sample.pdf"
    assert pdf.exists()
    return pdf


def test_every_page_is_half_letter(rendered):
    info = subprocess.run(
        ["pdfinfo", "-f", "1", "-l", "999", "-box", str(rendered)],
        capture_output=True, text=True, check=True,
    ).stdout
    boxes = re.findall(r"Page\s+\d+ MediaBox:\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)", info)
    assert boxes, info
    for width, height in boxes:
        assert abs(float(width) - HALF_LETTER_PT[0]) < TOLERANCE
        assert abs(float(height) - HALF_LETTER_PT[1]) < TOLERANCE


def test_render_carries_title_running_head_and_text_without_leaks(rendered):
    text = subprocess.run(
        ["pdftotext", str(rendered), "-"], capture_output=True, text=True, check=True
    ).stdout
    flat = re.sub(r"\s+", " ", text)
    assert "THE LAMP AT THE END OF THE PIER" in flat
    assert "by A. Sample" in flat
    assert "the lamp" in flat  # running head, small caps lowercased
    assert "It’s always two hundred and eleven in the daytime." in flat
    for leak in ("SSSceneBreak", "lettrine", "noindent", "***"):
        assert leak not in flat


def test_render_embeds_only_the_vendored_iowan_faces(rendered):
    fonts = subprocess.run(
        ["pdffonts", str(rendered)], capture_output=True, text=True, check=True
    ).stdout
    names = [line.split()[0] for line in fonts.splitlines()[2:] if line.strip()]
    assert names, fonts
    assert all("IowanOldStyle" in name for name in names), names
    assert any(name.endswith("IowanOldStyle-Titling") for name in names)
