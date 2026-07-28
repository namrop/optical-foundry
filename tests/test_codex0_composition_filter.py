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
    # Provisional 2026-07-28 print→scan calibration: digital heartword #800020
    # scanned as #863055; physical Writer's Blood scanned as #84315C. Applying
    # the same local Lab shift yields #7F0227 as the print-source ownvoice hex.
    assert codex_defaults["variables"]["ownvoice_color"] == "7F0227"

    spine_defaults = yaml.safe_load((PROFILE_ROOT / "defaults" / "document_spine.yaml").read_text())
    johannah_defaults = yaml.safe_load((PROFILE_ROOT / "defaults" / "mythic_letter_johannah.yaml").read_text())
    assert "filters" not in spine_defaults
    assert "filters" not in johannah_defaults


def test_codex_pataphorical_blocks_emit_page_ranges_and_role_length_pools(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-pataphorical}
The first field opens.

It continues long enough to need page coverage.
:::

Ordinary prose stays outside the field.

::: {.codex-pataphorical}
The second field opens.
:::
""",
    )

    assert latex.count("\\CodexPataphorBegin{") == 2
    assert latex.count("\\CodexPataphorEnd{") == 2
    assert "\\CodexPataphorBegin{1}" in latex
    assert "\\CodexPataphorEnd{1}" in latex
    assert "\\CodexPataphorBegin{2}" in latex
    assert "\\CodexPataphorEnd{2}" in latex
    assert latex.index("\\CodexPataphorBegin{1}") < latex.index("The first field opens")
    assert latex.index("The first field opens") < latex.index("\\CodexPataphorEnd{1}")

    # Pool declarations are emitted once, before the first range. Role and
    # line-band membership stay data-only; no folio-specific placement enters
    # the source.
    assert latex.count("\\CodexRailPoolReset") == 1
    assert "\\CodexRailPoolAdd{head}{4}{" in latex
    assert "H04B_head_04lines_scabiosa_exact_300ppi.png" in latex
    assert "\\CodexRailPoolAdd{head}{32}{" in latex
    assert "H32D_head_32lines_cow_vetch_exact_300ppi.png" in latex
    assert "\\CodexRailPoolAdd{tail}{4}{" in latex
    assert "T04B_tail_04lines_scabiosa_exact_300ppi.png" in latex
    assert "\\CodexRailPoolAdd{tail}{32}{" in latex
    assert "T32E_tail_32lines_lupine_exact_300ppi.png" in latex
    assert "\\CodexRailPoolAdd{body}{38}{" in latex
    assert "F22_body_38lines_lupine_dense_exact_300ppi.png" in latex
    assert "F29_body_38lines_lupine_quiet_exact_300ppi.png" in latex
    # Finite-to-finite legacy ladders remain available only to contained blocks.
    assert "\\CodexRailPoolAdd{contained}{4}{" in latex
    assert "RS01_lavender_sprig_tip_alpha.png" in latex
    assert "\\CodexRailPoolAdd{contained}{25}{" in latex
    assert "RL01_lavender_sheaf_tall_alpha.png" in latex
    assert latex.index("\\CodexRailPoolReset") < latex.index("\\CodexPataphorBegin{1}")
    assert "\\CodexRegisterRail" not in latex


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
    assert "\\definecolor{LetterOwnVoice}{HTML}{7F0227}" in template


def test_codex0_template_wires_pataphor_ranges_to_page_local_role_rails():
    template = (PROFILE_ROOT / "templates" / "codex0.tex").read_text()

    assert "\\NewDocumentCommand{\\CodexRailPoolReset}" in template
    assert "\\NewDocumentCommand{\\CodexRailPoolAdd}{m m m}" in template
    assert "\\NewDocumentCommand{\\CodexPataphorBegin}" in template
    assert "\\NewDocumentCommand{\\CodexPataphorEnd}" in template
    assert "\\usepackage{zref-savepos}" in template
    assert "\\zsavepos{codexpatstartpos@#1}" in template
    assert "\\zsavepos{codexpatendpos@#1}" in template
    assert "\\tl_new:N \\l_codex_rail_role_tl" in template
    assert "\\int_new:N \\l_codex_rail_band_int" in template
    assert "\\dim_new:N \\l_codex_rail_segment_top_dim" in template
    assert "\\dim_new:N \\l_codex_rail_segment_bottom_dim" in template
    assert "\\dim_new:N \\l_codex_rail_segment_height_dim" in template
    assert "\\codex_rail_select_role:" in template
    assert "\\codex_rail_select_band:" in template
    assert "\\codex_rail_select_seed:" in template
    # Height-only scaling: width floats proportionally, staying at or under
    # the design width. This eliminates the aspect-ratio cap that left gaps
    # on full-page head/tail segments.
    assert "height=#2" in template
    assert "width=#1,keepaspectratio" not in template
    assert "\\CodexShipoutPataphorRail" in template
    assert "\\AddToShipoutPictureBG{\\CodexShipoutPataphorRail}" in template
    # The old one-rail-per-page and whole-range tier state must be gone: two
    # distinct semantic blocks on one physical page each need their own segment.
    assert "l_codex_rail_page_claimed_bool" not in template
    assert "l_codex_rail_span_int" not in template
    # The shipout path must use physical-page parity and the already trim-shifted
    # margin separation, rather than a one-direction hspace that breaks versos.
    assert "\\int_if_odd:nTF { \\l_codex_rail_page_int }" in template
    assert "\\marginparsep" in template
    assert "\\CodexTrimAllowance" in template
    assert "\\CodexRailTextClearance" in template


def test_codex_pataphor_begin_enters_horizontal_mode_before_saving_first_position():
    template = (PROFILE_ROOT / "templates" / "codex0.tex").read_text()

    begin_macro = template.split(
        "\\NewDocumentCommand{\\CodexPataphorBegin}{m}", 1
    )[1].split("\\NewDocumentCommand{\\CodexPataphorEnd}{m}", 1)[0]
    assert "\\leavevmode" in begin_macro
    assert begin_macro.index("\\leavevmode") < begin_macro.index(
        "\\zref@labelbyprops{codexpatstart@#1}{abspage}"
    )
    assert begin_macro.index("\\leavevmode") < begin_macro.index(
        "\\zsavepos{codexpatstartpos@#1}"
    )


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
