"""Tests for Codex 0 profile-scoped composition grammar."""
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.profile_resolver import resolve_profile

GF = Path(__file__).resolve().parents[1]
PROFILE_ROOT = GF / "profiles" / "40_latex_import"
FILTER = PROFILE_ROOT / "filters" / "codex0_composition.lua"


def _pandoc_latex(tmp_path: Path, body: str) -> str:
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc not available")
    src = tmp_path / "codex-composition.md"
    src.write_text(body, encoding="utf-8")
    result = subprocess.run(
        ["pandoc", str(src), "-t", "latex", "--lua-filter", str(FILTER)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=PROFILE_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_codex_composition_filter_lowers_core_block_primitives(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-landing}
This lands.
:::

::: {.codex-breath}
This breathes.
:::

::: {.codex-vow}
This vows.
:::
""",
    )

    assert "\\begin{CodexLanding}{4}{0.45em}{0.70em}" in latex
    assert "\\end{CodexLanding}" in latex
    assert "\\begin{CodexBreath}{8}{0.45em}{0.60em}" in latex
    assert "\\begin{CodexVow}{5}{0.80em}{0.90em}" in latex


def test_codex_hinge_break_emits_bespoke_ornament_and_edge_companions(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-hinge-break ornament="assets/custom-hinge.png" edge="assets/edge.png" anchor="paragraph" wrap="true" ornament-width="0.40\linewidth" ornament-gap="0.25em" rail-width="0.42in"}
Then something turns.
:::
""",
    )

    assert "\\begin{CodexHingeBreak}{10}{0.90em}{1.00em}" in latex
    assert "\\CodexBreakOrnament[width=0.40\\linewidth][0.25em]{assets/custom-hinge.png}" in latex
    assert "\\CodexEdgeCompanion[0.42in][anchor=paragraph,wrap=true,width=0.42in]{assets/edge.png}" in latex


def test_codex_filter_supports_additional_visual_grammar_blocks_and_inline_signal(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-witness}
A witness arrives with [signal]{.codex-signal}.
:::

::: {.codex-axiom gap-before="0.2em" gap-after="0.3em"}
A page is not neutral.
:::

::: {.codex-tailpiece}
Let this close quietly.
:::
""",
    )

    assert "\\begin{CodexWitness}{5}{0.70em}{0.80em}" in latex
    assert "\\CodexSignal{signal}" in latex
    assert "\\begin{CodexAxiom}{5}{0.2em}{0.3em}" in latex
    assert "\\begin{CodexTailpiece}{6}{0.60em}{0.75em}" in latex


def test_codex_ownvoice_span_and_heartword_stacking(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
He said [I have done that a bunch]{.codex-ownvoice} and meant it.

A verbatim that is also a heartword: [it keeps me whole]{.codex-heartword .codex-ownvoice}.

A plain heartword stays accent-colored: [still here]{.codex-heartword}.
""",
    )

    assert "\\CodexOwnVoice{I have done that a bunch}" in latex
    assert "\\CodexOwnVoiceHeartword{it keeps" in latex  # pandoc may wrap inside the braces
    assert "\\CodexHeartword{still here}" in latex


def test_codex_quote_block_lowers_quote_with_author_source_and_date(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-quote author="Adrienne Rich" source="On Lies, Secrets, and Silence" date="1979"}
The possibilities that exist between two people, or among a group of people, are a kind of alchemy.
:::
""",
    )

    assert "\\begin{CodexQuoteBlock}{5}{0.70em}{0.85em}" in latex
    assert "The possibilities that exist" in latex
    assert "\\CodexQuoteAttribution{Adrienne Rich}{On Lies, Secrets, and Silence}{1979}" in latex
    assert "\\end{CodexQuoteBlock}" in latex


def test_codex_quote_block_allows_author_without_source_or_date(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-quote author="Adrienne Rich"}
The possibilities that exist between two people are a kind of alchemy.
:::
""",
    )

    assert "\\begin{CodexQuoteBlock}{5}{0.70em}{0.85em}" in latex
    assert "\\CodexQuoteAttribution{Adrienne Rich}{}{}" in latex
    assert "\\end{CodexQuoteBlock}" in latex


def test_codex_quote_block_allows_author_and_source_without_date(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-quote author="Adrienne Rich" source="On Lies, Secrets, and Silence"}
The possibilities that exist between two people are a kind of alchemy.
:::
""",
    )

    assert "\\CodexQuoteAttribution{Adrienne Rich}{On Lies, Secrets, and Silence}{}" in latex


def test_codex_quote_block_allows_author_and_date_without_source(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-quote author="Adrienne Rich" date="1979"}
The possibilities that exist between two people are a kind of alchemy.
:::
""",
    )

    assert "\\CodexQuoteAttribution{Adrienne Rich}{}{1979}" in latex


def test_codex_quote_block_escapes_attribution_metadata(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-quote author="A_B & C%" source="Work {Draft}" date="2026#1"}
Quoted text.
:::
""",
    )

    assert "\\CodexQuoteAttribution{A\\_B \\& C\\%}{Work \\{Draft\\}}{2026\\#1}" in latex


def test_codex_filter_lowers_editorial_note_divs(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-editorial-note kind="note" title="Revision lane"}
This is for Lux, not reader prose.

Preserve **Markdown** inside the note.
:::

> This is an ordinary blockquote.
""",
    )

    assert "\\begin{CodexEditorialNote}{note}{Revision lane}" in latex
    assert "This is for Lux" in latex
    assert "\\textbf{Markdown}" in latex
    assert "\\end{CodexEditorialNote}" in latex
    assert "\\begin{quote}" in latex
    assert "This is an ordinary blockquote" in latex


def test_codex_filter_uses_reclassified_default_asset_pools(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-breath}
First breath.
:::

::: {.codex-breath}
Second breath.
:::

::: {.codex-whisper}
A soft shift.
:::

::: {.codex-tailpiece}
A closing mark.
:::

::: {.codex-hinge-break}
A hinge turns.
:::

::: {.codex-threshold}
A threshold opens.
:::
""",
    )

    # Style map v2 r2 (2026-07-19): each pacing pool is one historical style;
    # breath is the Aldine leaf-fleuron FAMILY. Pool opens with the lightest
    # member (BR02, mirrored ivy pair); height-driven sizing.
    assert "style_map_v2_pools_2026-07-19/selected/breath/BR02_alpha.png" in latex
    assert "\\CodexBreakOrnament[height=1.7em][1\\baselineskip]" in latex
    # Whisper opens with the lightest copperplate flourish (WH05).
    assert "style_map_v2_pools_2026-07-19/selected/whisper/WH05_alpha.png" in latex
    assert "\\CodexBreakOrnament[height=2.0em][1.5\\baselineskip]" in latex
    assert "\\begin{CodexWhisper}" in latex
    # Tailpiece opens with the lightest cul-de-lampe (TL05).
    assert "style_map_v2_pools_2026-07-19/selected/tailpiece/TL05_alpha.png" in latex
    # Hinge opens with the lightest Rococo Fournier vignette (HN04).
    assert "style_map_v2_pools_2026-07-19/selected/hinge/HN04_alpha.png" in latex
    assert "\\CodexBreakOrnament[height=2.9em][2\\baselineskip]" in latex
    # Seal/threshold opens with the compass-rose volvelle.
    assert "style_map_v2_pools_2026-07-19/selected/seal/HS11_compass_alpha.png" in latex
    # Threshold stays width-driven.
    assert "\\CodexBreakOrnament[width=0.44\\linewidth][4\\baselineskip]" in latex


def test_codex_filter_supports_asset_id_overrides_for_primary_and_lane_specific_assets(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
::: {.codex-hinge-break asset="T03"}
Primary asset override.
:::

::: {.codex-hinge-break ornament-asset="FH12"}
Lane-specific overrides.
:::
""",
    )

    assert "hinge_candidate_03__T03__T03_seed_branch_closure" in latex
    assert "hinge_candidate_02__FH12__FH12_vine_tendrils" in latex


def test_codex_filter_ignores_unsafe_asset_paths_and_dimensions(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-hinge-break ornament="../escape.png" edge="assets/{bad}.png" ornament-width="1in}\evil{"}
Unsafe paths should not be emitted.
:::
""",
    )

    assert "\\begin{CodexHingeBreak}" in latex
    assert "CodexBreakOrnament" not in latex
    assert "CodexEdgeCompanion" not in latex
    assert "evil" not in latex
    assert "escape.png" not in latex


def test_codex0_profile_wires_filter_and_defaults_only_to_codex0():
    resolved = resolve_profile("codex0")
    assert [p.name for p in resolved.defaults_stack] == [
        "document_spine.yaml",
        "personal_letter.yaml",
        "mythic_letter_johannah.yaml",
        "codex0.yaml",
    ]
    assert resolved.template_path.name == "codex0.tex"

    codex_defaults = yaml.safe_load((PROFILE_ROOT / "defaults" / "codex0.yaml").read_text())
    assert codex_defaults["filters"] == ["filters/codex0_composition.lua"]
    assert codex_defaults["variables"]["codex_hinge_gap_before"] == "0.90em"
    assert codex_defaults["variables"]["codex_breath_ornament_gap"] == "1\\baselineskip"
    assert codex_defaults["variables"]["codex_hinge_ornament_gap"] == "2\\baselineskip"
    assert codex_defaults["variables"]["codex_threshold_ornament_gap"] == "4\\baselineskip"
    assert codex_defaults["variables"]["codex_quote_gap_after"] == "0.85em"
    assert codex_defaults["variables"]["codex_ornament_width"] == "0.44\\linewidth"

    spine_defaults = yaml.safe_load((PROFILE_ROOT / "defaults" / "document_spine.yaml").read_text())
    johannah_defaults = yaml.safe_load((PROFILE_ROOT / "defaults" / "mythic_letter_johannah.yaml").read_text())
    assert "filters" not in spine_defaults
    assert "filters" not in johannah_defaults


def test_codex0_template_exposes_composition_macros_and_environments():
    template = (PROFILE_ROOT / "templates" / "codex0.tex").read_text()

    assert "\\NewDocumentCommand{\\CodexBreakOrnament}" in template
    assert "\\CodexMaybeDecorativeImage" in template
    assert "\\NewDocumentCommand{\\CodexEdgeCompanion}" in template
    assert "\\newenvironment{CodexHingeBreak}" in template
    assert "\\newenvironment{CodexQuoteBlock}" in template
    assert "\\NewDocumentCommand{\\CodexQuoteAttribution}" in template
    assert "\\newenvironment{CodexEditorialNote}" in template
    assert "\\newenvironment{CodexWitness}" in template
    assert "\\providecommand{\\CodexSignal}" in template
    assert "\\providecommand{\\CodexOwnVoice}" in template
    assert "\\providecommand{\\CodexOwnVoiceHeartword}" in template
    assert "\\definecolor{LetterOwnVoice}{HTML}{432660}" in template


def test_codex_inline_rule_marker_lowers_to_wh10_flourish(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
First passage.

<!-- cx0:rule -->

Continuation passage.
""",
    )

    # Passage separator (2026-07-19): the WH10 copperplate swelled-rule flourish,
    # a centered image ornament, replaces the interim plain typographic rule.
    assert "\\CodexBreakOrnament[width=0.30\\linewidth]" in latex
    assert "style_map_v2_pools_2026-07-19/selected/rule/WH10_alpha.png" in latex


def test_codex_inline_rule_marker_honors_width_override(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
<!-- cx0:rule width="0.4\\linewidth" -->
""",
    )

    assert "\\CodexBreakOrnament[width=0.4\\linewidth]" in latex


def test_codex_inline_rule_marker_suppressed_by_asset_none(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        """
<!-- cx0:rule asset="none" -->
""",
    )

    assert "CodexBreakOrnament" not in latex
    assert "WH10_alpha.png" not in latex
