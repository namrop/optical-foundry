# Optical Foundry figure wraps

Source-level figure wraps are a general Optical Foundry layout primitive, not a Codex 0-only convention. Use fenced `of-image` blocks when prose should flow around an image inside the text measure; use the illumination rail / outer rail only when the image belongs outside the prose column.

## Basic wrap

```markdown
```of-image
path: assets/portrait.png
placement: wrap
side: right        # left | right; `align:` is also accepted
width: 0.34\textwidth
edge: none         # none | fade | vignette | soft
caption: Optional caption
```
```

For PDF/LaTeX profiles, the renderer lowers this to `wrapfigure` in a generated render-only Markdown copy. The authored source is not mutated.

## General tightening controls

Wrap fit varies by trim size, prose measure, image aspect ratio, and local paragraph shape. Tune the wrap in the source block rather than making profile-specific one-off macros:

```markdown
```of-image
path: assets/portrait.png
placement: wrap
side: left
width: 0.36\textwidth        # reserved wrap box
image_width: 0.92\linewidth  # rendered image inside the box
lines: 18                    # wrapfigure narrow-line count, 1–40
overhang: 0.04in             # wrapfigure overhang into the margin/gutter
sep: 0.055in                 # local \columnsep around the wrap
intextsep: 0pt               # local vertical float separation
raise: -0.2\baselineskip     # optional vertical nudge before the wrap
trim: 6pt 4pt 7pt 3pt        # graphicx trim: left bottom right top
clip: true
```
```

These controls are deliberately class-level: they work for any PDF/LaTeX profile that supports source-level layout images. Codex 0 can use them, but they are not owned by Codex 0.

## Displayed images: the whitespace contract

`placement: block` is the *displayed* lane — the image occupies flow on its own, with prose above and below rather than beside it. Two things are handled for it automatically, so that displayed images agree with each other across a whole work instead of each inheriting whatever whitespace its asset happened to be exported with:

```markdown
```of-image
path: assets/vignette.png
placement: block
width: 2.4in
gap: 2\baselineskip   # vertical envelope above and below; this is the default
auto_trim: true       # crop the blank margin the asset ships; this is the default
```
```

- **`gap`** replaces LaTeX's `center`/trivlist skips with one declared, rigid envelope. In the Codex 0 profile the default deliberately equals the hinge ornament's `hinge_ornament_gap`, so a displayed image sits in the page at the same weight as a hinge. Override per image when a passage genuinely wants a different weight.
- **`auto_trim`** measures the blank margin inside the asset's own canvas — object extracts are routinely exported on a generous canvas, and a soft vignette can fade below visibility well inside its bounding box — and crops it in a render-local twin. The declared width is scaled by the retained fraction, so the **visible** object keeps exactly the size it had: this removes whitespace, it never resizes artwork. An authored `trim:` always wins; `auto_trim: false` opts out; the source asset is never modified.

`placement: wrap` gets neither. A wrap has prose beside it, its vertical space is `\intextsep`, and a crop would move the figure inside the measure — use the explicit `trim:` control if a wrapped asset needs one.

Raw `\begin{center}\includegraphics[width=<absolute>]{path}\end{center}` lines written straight into source get the same displayed-image contract, so a work does not split into two spacing regimes depending on whether a given figure was wired as an `of-image` block. Full-page plates are excluded: the rewrite only fires on a line-initial match carrying a lone absolute `width=` and a brace-free literal path.

## Evidence surface

Each `of-image` block records a `layout_image` entry in the render evidence `figure_inventory`, including placement, side, width, edge mode, and any tightening controls (`wrapped_lines`, `overhang`, `sep`, `intextsep`, `raise`, `trim`, `clip`). Displayed images additionally record `gap`, an `origin` (`of_image_block` or `raw_centered_graphic`), and an `auto_trim` record with the measured margins, the fraction removed from each edge, and the authored path and width. Use this inventory to audit whether a proof was rendered with generic figure-wrap controls or only with default wrapping.

## Boundary with rails and plates

- Use `placement: wrap` for true inline wrapping where prose flows around the figure.
- Use `placement: inline` or `placement: block` when the figure should occupy flow without prose wrapping.
- Use the bound illumination / outer rail when the prose column must remain intact.
- Use source/witness plate wiring for facsimiles and full-page source objects; do not demote provenance plates into decorative wraps.

## Verification loop

1. Render a before/after proof with identical page geometry.
2. Inspect the generated evidence for `layout_image` entries and tuning fields.
3. Produce page contact sheets around affected pages.
4. Check for overlap, clipped text, awkward one-word lines, or excessive dead air.
5. For book objects, inspect at actual print size before treating screen-fit as final.
