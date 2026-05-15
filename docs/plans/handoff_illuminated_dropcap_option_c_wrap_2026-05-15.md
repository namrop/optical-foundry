---
uid: 019e2d03-28dd-78dd-8b37-111a36ae53fd
kind: note
note_role: handoff
validation_profile: standard
status: draft
created: 2026-05-15T14:58:00-04:00
updated: 2026-05-15T14:58:00-04:00
beam_home: 42_optical_foundry
title: "Handoff — Illuminated Drop Cap Option C Wrap Fix"
summary: "Implementation handoff for the Optical Foundry worker: Luis prefers Option C, the embedded-image illuminated initial, but the text wrap must be tightened so the first paragraph does not leave a large gap beside the initial."
tags:
  - optical-foundry
  - illuminated-codex
  - illuminated-drop-cap
  - codex-0
  - oasis-mythic
  - typography
  - handoff
---

# Handoff — Illuminated Drop Cap Option C Wrap Fix

## User decision

Luis reviewed the drop-cap mockups in the `#fonts` thread and selected **Option C** as the best direction:

> embedded-image illuminated initial / manuscript-style image initial

However, the current mockup leaves too much horizontal space between the illuminated image initial and the opening paragraph text. The implementation target is therefore:

> **Keep Option C’s embedded illuminated initial, but make the paragraph wrap correctly and tightly around it.**

This handoff is for the Optical Foundry worker.

## Context loaded before this handoff

Relevant Foundry planning anchor:

- `docs/plans/illuminated_letter_profile_path_2026-05-09.md`

Relevant conclusion from that planning note:

- Do **not** bake final prose into generated page images.
- Use generated/selected decorative assets as modules.
- LaTeX/Pandoc remains responsible for real text, pagination, and deterministic composition.
- Codex 0 should eventually get an illuminated-codex analogue: motif-driven section openers, semantic color roles, raster illustrations/seals/tailpieces, and readable typeset prose.

## Existing mockups

Generated-only mockups currently live at:

```text
42_optical_foundry/generated/font_dropcap_mockups_20260515/
```

Key rendered PDFs:

```text
42_optical_foundry/generated/font_dropcap_mockups_20260515/oasis_mythic/oasis_mythic_dropcap_font_mockups_2026-05-15.pdf
42_optical_foundry/generated/font_dropcap_mockups_20260515/codex0/codex0_dropcap_font_mockups_2026-05-15.pdf
```

Key mock source files:

```text
42_optical_foundry/generated/font_dropcap_mockups_20260515/sources/oasis_mythic_dropcap_font_mockups_2026-05-15.md
42_optical_foundry/generated/font_dropcap_mockups_20260515/sources/codex0_dropcap_font_mockups_2026-05-15.md
```

Key generated image-initial assets:

```text
42_optical_foundry/generated/font_dropcap_mockups_20260515/assets/t_illuminated_oasis.png
42_optical_foundry/generated/font_dropcap_mockups_20260515/assets/i_illuminated_codex0.png
```

These generated files are exploratory outputs and may be gitignored. Treat them as local evidence/examples, not canonical source assets unless explicitly promoted.

## Visual read of the mockups

The second-pass mockups successfully made the drop-cap treatments visible and distinct.

Strongest options:

- **Oasis Mythic:** Option C and Option B were strongest. Luis now prefers **Option C**.
- **Codex 0:** Option C has the strongest ceremonial/artifact signal. Option A remains a clean baseline, but the selected direction for this handoff is Option C.

Observed defects to fix:

- Text begins too far to the right of the image initial.
- The first wrapped lines feel loose/disconnected from the illuminated image.
- The wrap geometry is manually tuned rather than profile-owned.
- The current image initial works as proof-of-concept, but the asset should eventually be promoted/vendored if used beyond generated mockups.

## Implementation target

Create a reusable Optical Foundry / LaTeX surface for **embedded-image illuminated initials**.

The target behavior:

1. Place an image initial at the start of a paragraph.
2. Wrap the following text tightly around a rectangular initial block.
3. Expose tuning parameters for:
   - image path;
   - image width;
   - number of wrapped lines;
   - gap between image and text;
   - vertical nudge / baseline correction;
   - optional alt/live initial fallback policy.
4. Work in both:
   - `mythic` profile / letter-sized story renders;
   - `codex0` profile / A5 threshold-object renders.
5. Preserve deterministic text rendering: the paragraph text must remain real LaTeX/Pandoc text, not baked into an image.

## Recommended technical direction

### Preferred: profile macro using hanging indentation

The simplest robust path is a local profile macro that uses `\hangindent`, `\hangafter`, and a zero-width image box.

Sketch:

```tex
\newlength{\OFInitialWidth}
\newlength{\OFInitialGap}

% Args:
% 1 image path
% 2 image width, e.g. .84in
% 3 wrapped line count, e.g. 4
% 4 gap, e.g. .08in
% 5 vertical raise, e.g. -.72in
\newcommand{\OFImageInitialSetup}[5]{%
  \par\noindent
  \setlength{\OFInitialWidth}{#2}%
  \setlength{\OFInitialGap}{#4}%
  \hangindent=\dimexpr\OFInitialWidth+\OFInitialGap\relax
  \hangafter=-#3%
  \makebox[0pt][l]{\raisebox{#5}{\includegraphics[width=\OFInitialWidth]{#1}}}%
  \hspace{\dimexpr\OFInitialWidth+\OFInitialGap\relax}%
}
```

Usage shape:

```tex
\OFImageInitialSetup{assets/dropcaps/oasis/T.png}{.84in}{4}{.08in}{-.72in}%
hey awoke on a beach at the edge of the desert...
```

Why this direction:

- It avoids depending on `lettrine.sty`, which was absent from the local TeX Basic test environment.
- It avoids `wrapfigure` float behavior for the opening word.
- It gives direct control over the exact gap Luis objected to.
- It keeps all paragraph text live and selectable.

### Alternate: tuned `wrapfig`

`wrapfig` is available in the Foundry profile tree and can still be used, but the previous wrap-style experiments produced looser spacing and are easier to mis-tune.

If using `wrapfig`, make the gap explicit:

```tex
\setlength{\columnsep}{.08in}
\begin{wrapfigure}[4]{l}{.90in}
  \vspace{-1.0em}
  \includegraphics[width=.84in]{assets/dropcaps/oasis/T.png}
  \vspace{-1.0em}
\end{wrapfigure}
```

Acceptance still depends on screenshot review, because `wrapfig` can interact awkwardly with headings, lists, and short paragraphs.

## Profile/code placement recommendation

If this becomes a real profile feature, prefer adding the macro in the local Optical Foundry imported profile layer, not in source `40_latex`:

```text
42_optical_foundry/profiles/40_latex_import/styles/texmf/tex/latex/yugen/yugencommon.sty
```

or a small dedicated package such as:

```text
42_optical_foundry/profiles/40_latex_import/styles/texmf/tex/latex/yugen/yugenillumination.sty
```

Then load it from the relevant templates/profiles.

Do **not** mutate:

```text
40_latex/
```

unless Luis explicitly asks to patch the known-good reference renderer.

If implementation requires code/template changes, use a development branch in the `42_optical_foundry` repo, for example:

```bash
git checkout -b dev/illuminated-dropcap-option-c-wrap
```

No `dev` branch was present at handoff creation time.

## Asset policy

The mockups used temporary OFL fonts and generated image initials:

Temporary font source examples:

```text
~/.openclaw/workspace/font_specimens/nonlocal_fonts/google_ofl/EB_Garamond.ttf
~/.openclaw/workspace/font_specimens/nonlocal_fonts/google_ofl/Cormorant_Garamond.ttf
~/.openclaw/workspace/font_specimens/nonlocal_fonts/google_ofl/Crimson_Pro.ttf
~/.openclaw/workspace/font_specimens/nonlocal_fonts/google_ofl/Castoro.ttf
```

Production-ish Foundry work should not depend on workspace scratch font paths. If a font is selected, either:

1. install it system-wide and reference it by family name, or
2. vendor the OFL font files under a Foundry asset/font path and resolve them explicitly.

For image initials, prefer a profile-owned asset path such as:

```text
42_optical_foundry/profiles/40_latex_import/assets/dropcaps/oasis/
42_optical_foundry/profiles/40_latex_import/assets/dropcaps/codex0/
```

or an artifact-specific asset folder if the initials are unique to one story/packet.

## Acceptance criteria

A finished worker pass should produce:

1. A new or updated mockup PDF for **Oasis Mythic Option C** using the `mythic` profile.
2. A new or updated mockup PDF for **Codex 0 Option C** using the `codex0` profile.
3. Text wrap with no large gap beside the illuminated initial.
   - Target visual gap: roughly `.06in` to `.12in` between image block and text.
   - First 3–4 lines should visibly wrap beside the image.
4. No baked body text inside images.
5. Evidence JSON reports:
   - `success: true`;
   - no warnings, or explained warnings;
   - `target_40_latex_mutated: false`.
6. Screenshot/contact-sheet evidence for visual review.
7. If code was changed, tests/profile checks should pass for the touched profiles or explain residual gaps.

## Suggested validation commands

From the Foundry repo:

```bash
cd ~/Digital_Workspace/42_optical_foundry
python3.14 -m cli profiles --profile mythic
python3.14 -m cli profiles --profile codex0
```

Render commands should follow the normal Foundry shape:

```bash
python3.14 -m cli doc <mock-source.md> --profile mythic --output generated/<run-name>/oasis_mythic
python3.14 -m cli doc <mock-source.md> --profile codex0 --output generated/<run-name>/codex0
```

Rasterize PDFs for review:

```bash
pdftoppm -png -r 144 <output.pdf> generated/<run-name>/previews/page
```

## Non-goals

- Do not implement generalized page-composition mode.
- Do not bake final prose into generated page images.
- Do not contact vendors, install system fonts, or mutate production config without Luis approval.
- Do not overfit only to the temporary generated `T` and `I` assets; the macro should support arbitrary image initials.
- Do not promote mockup artifacts as proposal-ready, print-ready, or production-ready.

## One-line worker brief

Implement and validate **Option C: embedded illuminated image initials** for the Mythic and Codex 0 profiles, with tight deterministic text wrap around the initial image and no large paragraph gap.
