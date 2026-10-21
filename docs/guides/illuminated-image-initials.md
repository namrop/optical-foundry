# Illuminated Image Initials: Asset Size and Tuning Guide

Status: implemented guide for the source-level `of-initial` lane.

This guide covers image initials that are artwork, while the paragraph text remains live/selectable text. The source-facing surface is an `of-initial` fenced block lowered by Optical Foundry into a local LaTeX macro.

## Profile support

`of-initial` is expected to work for profiles that meet all of these conditions:

- render through the PDF/LaTeX Pandoc renderer;
- use a `.tex` template with a working `$for(header-includes)$ ... $endfor$` hook;
- inherit the local `profiles/40_latex_import` TeX path so `yugenillumination.sty` resolves;
- can resolve `assets/dropcaps/...` through generated `\graphicspath` roots;
- are not fixed-object sheet lanes where paragraph flow is not the layout model.

Validated smoke profiles from the initial implementation:

- `mythic` on letter paper;
- `codex0` on A5 paper.

Likely-compatible document-spine profiles include `cam`, `keeper`, `convergence`, `life`, and the Yugen document variants, but they should get a quick render smoke before claiming final support because each profile has its own type size, leading, margins, and template density.

Do not assume support for label sheets, sticker sheets, posters, resumes, or other non-prose/fixed-layout profiles without a separate profile-specific smoke.

## Source block

````markdown
```of-initial
path: assets/dropcaps/oasis/T.png
width: .84in
lines: 4
gap: .08in
raise: 0in
align: bottom
```
hey awoke on a beach...
````

The image supplies the visible initial letter. The following paragraph should begin after that letter, e.g. `hey...` for an image `T` or `n...` for an image `I`.

Important: the fenced block and the paragraph text must lower into the same paragraph. If the image appears detached above the paragraph, the macro/paragraph boundary has been broken.

````markdown
```of-initial
recipe: mythic_letter_default
path: assets/dropcaps/oasis/T.png
```
hey awoke on a beach...
````

Explicit tuning can override any recipe value:

````markdown
```of-initial
recipe: codex0_a5_default
path: assets/dropcaps/codex0/I.png
gap: .09in
lines: 4
```
n the beginning...
````

Named recipes currently exposed by the CLI:

- `codex0_a5_default`: `width: .72in`, `lines: 4`, `gap: .06in`, `raise: 0in`, `align: bottom`.
- `mythic_letter_default`: `width: .84in`, `lines: 4`, `gap: .08in`, `raise: 0in`, `align: bottom`.
- `cam_letter_default`: `width: .80in`, `lines: 4`, `gap: .08in`, `raise: 0in`, `align: bottom`.
- `generic_report_default`: `width: .78in`, `lines: 4`, `gap: .08in`, `raise: 0in`, `align: bottom`.

List recipes from the repo root with:

```bash
python3.14 -m cli initial recipes
```

## Asset format

Preferred asset properties:

- Format: transparent PNG.
- Color: RGB/RGBA PNG with alpha; avoid flattening onto white unless intentionally desired.
- Shape: square or near-square artwork is easiest to tune.
- Canvas: include only intentional ornament/air; crop dead transparent margin tightly.
- Minimum raster size: 512 x 512 px.
- Preferred raster size: 768 x 768 px to 1200 x 1200 px.
- Upper practical raster size: about 1600 x 1600 px unless the artwork needs very fine detail.

The PDF render uses the TeX `width` value, not the pixel dimensions, to size the image on the page. Pixels mainly control sharpness. At typical dropcap sizes, 512 px is already enough; 768-1200 px gives extra headroom for print.

## Starting sizes by page/profile class

Use these as first-pass values, then tune visually.

- A5 / dense codex profile:
  - `width: .62in` to `.76in`
  - `lines: 3` or `4`
  - `gap: .05in` to `.08in`
  - `align: bottom`

- Letter / normal document-spine profile:
  - `width: .78in` to `.95in`
  - `lines: 4`
  - `gap: .06in` to `.10in`
  - `align: bottom`

- Large ceremonial opener on letter:
  - `width: .95in` to `1.20in`
  - `lines: 4` or `5`
  - `gap: .08in` to `.12in`
  - `align: bottom`

- Compact inline flourish:
  - `width: .45in` to `.60in`
  - `lines: 2` or `3`
  - `gap: .04in` to `.07in`
  - `align: top` or `bottom`, whichever visually anchors better.

Validated initial smoke values:

- `codex0` A5: `width: .72in`, `lines: 4`, `gap: .06in`, `align: bottom`.
- `mythic` letter: `width: .84in`, `lines: 4`, `gap: .08in`, `align: bottom`.

## Width, line count, and gap relationship

The macro creates a hanging paragraph. Conceptually:

- `width` is the rendered image width.
- `gap` is the whitespace between image box and live text.
- `lines` is how many opening lines reserve the hanging indent.
- effective reserved horizontal space is approximately `width + gap`.

If the paragraph feels too loose horizontally, reduce `gap` first. If it still feels detached, reduce `width` slightly or use a more tightly cropped asset.

If the paragraph collides with the ornament, increase `gap` in `.01in` or `.02in` increments.

Target visual gap for the Option C style: about `.06in` to `.12in`, with `.06in`-`.08in` usually better for tight illuminated initials.

## Vertical alignment

Supported values:

- `align: top`
- `align: bottom`

Use `align: top` for historically styled dropped initials where the top of the image should align with the opening text block and the image should descend through a fixed number of reserved lines. This is the safer default for book/manuscript-style chapter openers.

Use `align: bottom` for letter-style or ceremonial initials where the image should visually anchor against the bottom of the wrapped text block.

The choice is a source/artifact tuning decision, not a separate profile. Use `raise` for fine correction:

- `raise: .03in` nudges the image up.
- `raise: -.03in` nudges the image down.

Avoid large `raise` values unless deliberately designing a special opener. If the value needs to exceed about `.12in`, the asset crop, width, or line count is probably wrong.

## Image crop rules

Most bad spacing comes from the image canvas, not the macro.

Recommended crop policy:

- Crop transparent margin tightly around the ornamental frame.
- Keep only deliberate internal breathing room.
- If the artwork has a heavy border, ensure the border itself is what defines the image edge.
- Avoid giant transparent side margins; they count as part of `width` and make the text appear too far away even when `gap` is small.

When text looks too far from the image but `gap` is already around `.06in`, inspect the PNG canvas before changing code.

The Foundry CLI can report alpha bounds and a crop box for transparent PNG drop caps:

```bash
python3.14 -m cli initial inspect profiles/40_latex_import/assets/dropcaps/oasis/T.png
```

The report includes:

- `alpha_bbox_px`: visible non-transparent bounds;
- `transparent_margins_px`: invisible canvas on each side;
- `recommended_crop_box_px`: `left,top,right,bottom` crop box with right/bottom exclusive;
- `needs_crop_attention`: true when the transparent margin fraction is large enough to explain suspicious spacing.

## Profile-specific tuning loop

For a new profile:

1. Start with the closest page-class values above.
2. Render one smoke page with a short first paragraph and one normal second paragraph.
3. Rasterize page 1 or make a contact sheet.
4. Check:
   - image is present;
   - no raw macro text appears;
   - no visible `%` appears;
   - first 3-4 lines wrap beside the image;
   - normal paragraph flow resumes after the image block;
   - body text remains live/selectable in the PDF;
   - evidence warnings are empty or explained;
   - `target_legacy_profile_tree_mutated: false`.
5. Tune in this order:
   - crop transparent image margin;
   - `gap`;
   - `width`;
   - `lines`;
   - `raise`;
   - `align`.

## Recommended asset paths

Use profile-owned stable paths under the local Foundry import:

- `profiles/40_latex_import/assets/dropcaps/oasis/T.png`
- `profiles/40_latex_import/assets/dropcaps/<profile-or-style>/<letter>.png`
- in a profile package, `<package>/assets/dropcaps/<style>/<letter>.png` with the package directory on its
  `tex:` list; the Codex 0 `I.png` is `codex0-a5/assets/dropcaps/codex0/I.png` in
  `optical-foundry-profiles` (SIL-31, 2026-10-21)

Source references should use relative render-resource paths:

- `assets/dropcaps/oasis/T.png`
- `assets/dropcaps/codex0/I.png`

Do not reference scratch-generation paths, absolute paths, URLs, or parent traversal paths.

## Failure symptoms

- Image appears above the paragraph rather than beside it:
  - macro and paragraph became separate paragraphs;
  - check fenced-block newline handling.

- Text starts with a visible `%`:
  - generated macro swallowed/printed spacing incorrectly;
  - macro should be followed by an explicit space, not a visible `%` artifact.

- Text is too far from image:
  - reduce `gap`;
  - crop transparent side margins;
  - reduce `width` if the artwork is visually too wide.

- Text overlaps ornament:
  - increase `gap`;
  - increase `width` only if the image needs more physical size, not as a spacing fix;
  - check crop and transparent padding.

- Image missing but PDF renders:
  - check `layout_image_graphicspath_roots` in evidence;
  - verify the asset lives under `profiles/40_latex_import/assets/...` or beside the source;
  - verify the path is relative and uses `.png`, `.jpg`, `.jpeg`, or `.pdf`.

## Security and path boundary

Because this lowers to raw LaTeX, image paths and dimensions are constrained. Paths must be relative render-resource paths. Reject or avoid:

- absolute paths;
- parent traversal (`..`);
- URLs;
- control characters;
- TeX-sensitive characters in path values;
- unsafe image extensions.

Filesystem roots added to generated `\graphicspath` must also avoid TeX-dangerous characters such as `%`, `#`, `$`, braces, backticks, backslashes, URL syntax, or control characters. If a render fails on that boundary, move the source/output tree to a simpler path and rerender.
