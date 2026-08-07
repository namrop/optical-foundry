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
    # Whisper opens with the lightest copperplate flourish (WH05). Retuned
    # 2026-08-06 (Luis-blessed) from 2.0em/1.5bl: the taxonomy re-ruling made
    # whisper the LIGHTEST tier, so it now sits below the breath, not above it.
    assert "style_map_v2_pools_2026-07-19/selected/whisper/WH05_alpha.png" in latex
    assert "\\CodexBreakOrnament[height=1.0em][0.5\\baselineskip]" in latex
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

    # Contained-only grammar (Luis, 2026-08-02). Every rail is a complete plant,
    # finite at both ends, drawn natively at its line length. The endpoint roles
    # (head/tail) and the open/open body role are retired from emission: a
    # multi-page passage draws a distinct contained specimen per page rather
    # than continuing one stem across the spread.
    for retired_role in ("head", "tail", "body"):
        assert f"\\CodexRailPoolAdd{{{retired_role}}}{{" not in latex

    # The ladder is emitted at 2-line rungs, 2..38, contained role only.
    rungs = list(range(2, 39, 2))
    for rung in rungs:
        assert f"\\CodexRailPoolAdd{{contained}}{{{rung}}}{{" in latex
    assert latex.count("\\CodexRailPoolAdd{") == 58

    # Rung membership comes from the solved ladder allocation. Spot-check the
    # two ends: the shortest bloom marks and the full-text-block rails.
    assert "CL32_new_england_aster_mid_alpha.png" in latex          # 2L
    assert "CL15_purple_loosestrife_tall_2x_alpha.png" in latex     # 38L, venice 2x
    assert latex.count("\\CodexRailPoolAdd{contained}{38}{") == 9

    # Edge-touching (open) families are excluded under contained-only: the whole
    # G* gap-fill and RX* XL-probe sets run off the canvas top/bottom.
    for open_asset in ("G7D_lavender", "G7E_cow_vetch", "G6A_lavender", "RX01_lavender", "RX04_clematis"):
        assert open_asset not in latex
    # Integral open/open body assets are likewise no longer wired.
    assert "S38BV02E_blue_vervain_integral_38lines_exact_300ppi.png" not in latex
    # Morphology failures stay out.
    assert "RS01_lavender_sprig_tip_alpha.png" not in latex
    assert "H32D_head_32lines_cow_vetch_exact_300ppi.png" not in latex

    assert latex.index("\\CodexRailPoolReset") < latex.index("\\CodexPataphorBegin{1}")
    assert "\\CodexRegisterRail" not in latex


def _pataphor_markers(latex):
    """Return ordered [(kind, seg, run), ...] for every \\CodexPataphorBegin/End.

    Markers are \\CodexPataphorBegin{seg}{run} / \\CodexPataphorEnd{seg}{run}
    (per-segment drawing, 2026-08-02): seg id is the per-div draw extent, run id
    is the story family/seed key.
    """
    import re
    return [
        (m.group(1), int(m.group(2)), int(m.group(3)))
        for m in re.finditer(r"\\CodexPataphor(Begin|End)\{(\d+)\}\{(\d+)\}", latex)
    ]


def test_codex_pataphorical_same_story_divs_share_a_run_but_draw_as_separate_segments(tmp_path):
    # Story-scoped runs (Capability A, 2026-08-02): consecutive .codex-pataphorical
    # divs sharing story= share ONE run id (seed/family key). But per-segment
    # drawing (Luis-caught in Apertures) means each div is its OWN segment with its
    # own Begin+End, so the literal-prose interlude BETWEEN them draws no rail --
    # the run no longer paints a hull across the gap.
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-pataphorical story="boy"}
The first field opens.
:::

Ordinary prose interlude stays outside the field.

::: {.codex-pataphorical story="boy"}
The same story resumes.
:::
""",
    )

    markers = _pataphor_markers(latex)
    begins = [m for m in markers if m[0] == "Begin"]
    ends = [m for m in markers if m[0] == "End"]
    # Two segments, each fully bracketed by its own Begin and End (so each draws on
    # its own pages, and nothing spans the interlude between them).
    assert len(begins) == 2 and len(ends) == 2
    begin_segs = {seg for _, seg, _ in begins}
    end_segs = {seg for _, seg, _ in ends}
    assert begin_segs == end_segs  # every segment is individually opened and closed
    assert len(begin_segs) == 2  # two DISTINCT segments, not one hull
    # ...but both segments carry the SAME run id, so the story reads as one family.
    assert {run for _, _, run in begins} == {1}


def test_codex_pataphorical_story_change_starts_a_new_run(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-pataphorical story="girl"}
Her telling opens the chapter.
:::

::: {.codex-pataphorical story="both"}
The shared telling begins.
:::
""",
    )

    begins = [m for m in _pataphor_markers(latex) if m[0] == "Begin"]
    # girl -> run 1 (seg 1), both -> run 2 (seg 2): two segments, two runs.
    assert [(seg, run) for _, seg, run in begins] == [(1, 1), (2, 2)]
    assert latex.index("\\CodexPataphorBegin{1}{1}") < latex.index("Her telling")
    assert latex.index("\\CodexPataphorBegin{2}{2}") < latex.index("The shared telling")


def test_codex_pataphorical_run_resets_at_a_chapter_opener(tmp_path):
    # A chapter opener (\OFSetRunningTagline raw block, as the manifest emits it)
    # resets the run state, so same-story divs on opposite sides of a chapter
    # boundary land in DIFFERENT runs -- a story family can never cross a chapter.
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-pataphorical story="boy"}
The boy's tale, chapter one.
:::

\OFSetRunningTagline{Chapter Two}

::: {.codex-pataphorical story="boy"}
The boy's tale, chapter two, must not merge with chapter one.
:::
""",
    )

    begins = [m for m in _pataphor_markers(latex) if m[0] == "Begin"]
    # Identical story, but the opener reset means run ids differ.
    assert [run for _, _, run in begins] == [1, 2]


def test_codex_pataphorical_run_resets_at_a_part_divider(tmp_path):
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-pataphorical story="realm"}
Realm telling before the part divider.
:::

\OFSetRunningDivision{Part XII}

::: {.codex-pataphorical story="realm"}
Realm telling after the part divider must not merge.
:::
""",
    )

    begins = [m for m in _pataphor_markers(latex) if m[0] == "Begin"]
    assert [run for _, _, run in begins] == [1, 2]


def test_codex_pataphorical_untagged_div_falls_back_to_its_own_run(tmp_path):
    # An untagged div must never silently merge into a neighbor; it gets a
    # standalone run and does not share a family with the tagged div beside it,
    # nor with a second untagged div.
    latex = _pandoc_latex(
        tmp_path,
        r"""
::: {.codex-pataphorical story="boy"}
Tagged boy telling.
:::

::: {.codex-pataphorical}
Untagged div one.
:::

::: {.codex-pataphorical}
Untagged div two.
:::
""",
    )

    markers = _pataphor_markers(latex)
    begins = [m for m in markers if m[0] == "Begin"]
    ends = [m for m in markers if m[0] == "End"]
    # Three segments, three runs (boy 1, untagged 2, untagged 3): none merge.
    assert [(seg, run) for _, seg, run in begins] == [(1, 1), (2, 2), (3, 3)]
    assert len(ends) == 3


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
    # Per-segment drawing (2026-08-02): Begin/End take {seg}{run}; the seg id keys
    # the draw-extent labels, the run id keys the seed via \g_codex_seg_run_prop.
    assert "\\NewDocumentCommand{\\CodexPataphorBegin}{m m}" in template
    assert "\\NewDocumentCommand{\\CodexPataphorEnd}{m m}" in template
    assert "\\prop_new:N \\g_codex_seg_run_prop" in template
    assert "\\prop_gput:Nnn \\g_codex_seg_run_prop {#1} {#2}" in template
    assert "\\prop_get:NnNF \\g_codex_seg_run_prop {#1} \\l_codex_rail_run_tl" in template
    assert "\\codex_rail_select_seed:n { \\l_codex_rail_run_int }" in template
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
    # Contained-only: the role is fixed, so pool membership is decided purely by
    # the measured line length. The endpoint/body branch on page position is gone.
    assert "\\tl_set:Nn \\l_codex_rail_role_tl {head}" not in template
    assert "\\tl_set:Nn \\l_codex_rail_role_tl {tail}" not in template
    assert "\\tl_set:Nn \\l_codex_rail_role_tl {body}" not in template
    # Stub floor (Keeper-ratified 2026-08-06, audit verdict f.478): a page-local
    # segment below the smallest promoted asset band (04 lines) must draw
    # nothing rather than pull the 2L rung and leave a vestigial stub.
    assert "\\int_new:N \\g_codex_rail_min_lines_int" in template
    assert "\\int_gset:Nn \\g_codex_rail_min_lines_int {4}" in template
    assert "\\NewDocumentCommand{\\CodexRailSetMinLines}{m}" in template
    assert (
        "< { \\int_use:N \\g_codex_rail_min_lines_int \\baselineskip }" in template
    )
    # Rungs are 2-line and the measured segment rounds UP, so a selected asset
    # is always at least as slender as its slot and can never be width-capped.
    assert "\\fp_to_int:n" in template
    assert "ceil" in template
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
    # Fore-edge parity must key off the page counter -- the same counter LaTeX
    # uses to pick \oddsidemargin vs \evensidemargin -- NOT the physical
    # abspage. Keying off abspage silently throws every rail into the gutter as
    # soon as the frontmatter page count shifts by one (2026-08-02: the Edition
    # Notice spilling to a second leaf did exactly that).
    assert "\\int_if_odd:nTF { \\value{page} }" in template
    assert "\\int_if_odd:nTF { \\l_codex_rail_page_int }" not in template
    assert "\\marginparsep" in template
    assert "\\CodexTrimAllowance" in template
    assert "\\CodexRailTextClearance" in template


def test_codex_pataphor_begin_enters_horizontal_mode_before_saving_first_position():
    template = (PROFILE_ROOT / "templates" / "codex0.tex").read_text()

    begin_macro = template.split(
        "\\NewDocumentCommand{\\CodexPataphorBegin}{m m}", 1
    )[1].split("\\NewDocumentCommand{\\CodexPataphorEnd}{m m}", 1)[0]
    assert "\\leavevmode" in begin_macro
    assert begin_macro.index("\\leavevmode") < begin_macro.index(
        "\\zref@labelbyprops{codexpatstart@#1}{abspage}"
    )
    assert begin_macro.index("\\leavevmode") < begin_macro.index(
        "\\zsavepos{codexpatstartpos@#1}"
    )


def test_every_inline_ornament_marker_lowers_to_its_own_pool(tmp_path):
    """Each in-passage cx0 ornament marker must reach its own asset pool.

    Regression guard for the 2026-08-06 ornament-taxonomy re-ruling. The sweep
    rewrote every in-passage `cx0:breath` to `cx0:whisper` in the spine, but the
    filter's `inline_ornament_by_marker` table had no `whisper` entry — and
    unknown cx0 markers fail QUIET (pandoc drops the HTML comment), so all 192
    spine whispers rendered as nothing at all in build 48. A marker that names a
    real pool must never silently render as nothing.
    """
    latex = _pandoc_latex(
        tmp_path,
        """
Opening paragraph.

<!-- cx0:whisper -->

After the whisper.

<!-- cx0:breath -->

After the breath.

<!-- cx0:hinge -->

After the hinge.
""",
    )

    # whisper — copperplate penwork, the lightest in-passage pause post-re-ruling
    assert "style_map_v2_pools_2026-07-19/selected/whisper/WH05_alpha.png" in latex
    # breath — Aldine leaf-fleuron family, now the ex-hinge in-passage tier
    assert "style_map_v2_pools_2026-07-19/selected/breath/BR02_alpha.png" in latex
    # hinge — Rococo Fournier, now the mechanical between-passage separator only
    assert "style_map_v2_pools_2026-07-19/selected/hinge/HN04_alpha.png" in latex
    assert latex.count("\\CodexBreakOrnament") == 3


def test_inline_ornament_marker_table_covers_every_height_tuned_pool():
    """Any pool with a `*_ornament_height` default must be reachable inline.

    The whisper regression was invisible because the pool, the gap default and
    the height default all existed — only the marker-table entry was missing.
    Tie the three together so the next tier added cannot half-land.
    """
    lua = FILTER.read_text(encoding="utf-8")
    table = lua.split("local inline_ornament_by_marker = {", 1)[1].split("\n}", 1)[0]
    import re

    tuned = set(re.findall(r"^\s*(\w+)_ornament_height\s*=", lua, re.MULTILINE))
    wired = set(re.findall(r"^\s*(\w+)\s*=\s*\{", table, re.MULTILINE))
    assert tuned <= wired, f"height-tuned pools with no inline marker: {tuned - wired}"


def test_in_passage_ornament_ladder_reads_hinge_over_breath_over_whisper():
    """The three pause tiers must stay ordered in BOTH dimensions.

    Luis-blessed 2026-08-06. The ornament-taxonomy re-ruling made whisper the
    lightest in-passage pause, but it was still carrying the weights it got on
    2026-07-07 when whisper meant "a soft turn rather than a pause" — heavier
    than the breath. That shipped the ex-breath sites MORE space than the state
    the re-ruling exists to fix. Lock the ordering so it cannot silently invert
    again when a tier is retuned.
    """
    import re

    lua = FILTER.read_text(encoding="utf-8")

    def default(key):
        m = re.search(rf'^\s*{key}\s*=\s*"([^"]+)"', lua, re.MULTILINE)
        assert m, f"missing default: {key}"
        return m.group(1)

    def number(value):
        return float(re.match(r"^([\d.]+)", value).group(1))

    heights = {t: number(default(f"{t}_ornament_height")) for t in ("whisper", "breath", "hinge")}
    gaps = {t: number(default(f"{t}_ornament_gap")) for t in ("whisper", "breath", "hinge")}

    assert heights["whisper"] < heights["breath"] < heights["hinge"], heights
    assert gaps["whisper"] < gaps["breath"] < gaps["hinge"], gaps

    # The blessed values themselves, so a retune is a deliberate edit here too.
    # Note the doubled backslash: these are read as Lua source literals.
    assert default("whisper_ornament_height") == "1.0em"
    assert default("whisper_ornament_gap") == "0.5\\\\baselineskip"
    assert default("breath_ornament_height") == "1.7em"
    assert default("hinge_ornament_height") == "2.9em"


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
