# Handoff — Codex 0 endnotes wiring (footnotes → back-matter endnotes)

Date: 2026-07-06
Requested by: Luis (codex0_v5 book lane)
Owner of this task: the Optical Foundry session
Related brief: `docs/plans/2026-07-05-book-production-mechanics-upstream-and-v5-support-brief.md`

## Goal

Codex 0 v5 authors reference notes as inline pandoc footnotes (`[^id]` … `[^id]: …`)
in the passage markdown. Today the codex0 profile renders these as inline
bottom-of-page `\footnote`s. Luis wants them to instead **collect into a single
back-matter Notes section**, auto-numbered in reading order, so that:

- the five existing Part IX ch.2 convergence-log footnotes get a real home, and
- any footnote added later, anywhere in the book, flows to the same Notes
  section with **no manifest edit and no per-note bookkeeping**.

The Atrium-side print sink is already in place (see "Atrium side, already done"
below). This handoff is only the OF-side preamble wiring, which cannot be done
from the bundle manifest (the `_guard_manifest_variables` allowlist in
`engine/manifest_compiler.py` intentionally rejects list-valued / LaTeX-control-token
variables like `header-includes`, so preamble injection must live in the profile
or template).

## What to change (OF side)

Wire the `endnotes` package into the **codex0 lane only** — do not touch other
profiles. Two viable homes; pick whichever fits OF conventions:

- `profiles/40_latex_import/templates/codex0.tex` (it already has a
  `$for(header-includes)$` hook near line 570 and its own `\usepackage` block), or
- `profiles/40_latex_import/defaults/codex0.yaml` (add a `header-includes` entry).

Minimum preamble:

```latex
\usepackage{endnotes}
\let\footnote\endnote
```

`\let\footnote\endnote` globally remaps pandoc's emitted `\footnote{…}` to
`\endnote{…}`, so no per-note or per-source change is needed.

## Details / gotchas to resolve

1. **Engine.** codex0 renders under **lualatex** (`codex0.yaml: pdf-engine: lualatex`),
   not xelatex. `endnotes` works under lualatex; just confirm on a probe render.

2. **Heading duplication.** The Atrium print sink calls `\theendnotes` from within
   `backmatter/01_notes_endnotes_placeholder.md`, and that markdown already emits a
   `# Notes` heading. The sink empties `\notesname` locally
   (`\renewcommand{\notesname}{}`) so the package's own heading does not double it.
   If you prefer the package to own the heading instead, coordinate before changing
   the markdown — don't produce two "Notes" headings.

3. **`\theendnotes` placement is Atrium-owned.** Do **not** add `\theendnotes` in the
   template. It lives in the backmatter markdown so the notes land in the correct
   back-matter position in the spine. The template only needs the package + remap.

4. **Composition filter interaction.** codex0 uses
   `filters/codex0_composition.lua`. Please confirm the footnote→endnote remap does
   not collide with any footnote/verse/vow handling in that filter (a probe render of
   Part IX ch.2 — which has five real footnotes — is the fastest check).

5. **Reset behavior.** Endnotes should number continuously across the whole book
   (single Notes section at the end), not per-part. Default `endnotes` behavior is
   continuous; just verify no `\setcounter{endnote}{0}` sneaks in via dividers.

6. **Frontmatter footnotes.** The remap is global, so any `\footnote` in frontmatter
   (e.g. foreword) would also become an endnote. Current frontmatter has none; flag
   it if that changes.

## Atrium side, already done (for your context)

- `21_letters_and_creative/book/codex0_v5/backmatter/01_notes_endnotes_placeholder.md`
  now contains the guarded print sink:

  ```latex
  \ifdefined\theendnotes\begingroup\renewcommand{\notesname}{}\theendnotes\endgroup\fi
  ```

  It is inert (renders nothing) until this OF patch defines `\theendnotes`, then
  lights up automatically. No Atrium change is needed once you land the preamble.

## Acceptance check

Probe-render Part IX ch.2 (or the full book) via the codex0 bundle manifest and
confirm: (a) the five `[^18b-…]` footnotes no longer print at the bottom of their
pages, (b) they appear as a numbered list in the back-matter Notes section under the
single `# Notes` heading, in reading order, with working links if hyperref is active.
