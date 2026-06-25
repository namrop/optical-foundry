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

## Evidence surface

Each `of-image` block records a `layout_image` entry in the render evidence `figure_inventory`, including placement, side, width, edge mode, and any tightening controls (`wrapped_lines`, `overhang`, `sep`, `intextsep`, `raise`, `trim`, `clip`). Use this inventory to audit whether a proof was rendered with generic figure-wrap controls or only with default wrapping.

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
