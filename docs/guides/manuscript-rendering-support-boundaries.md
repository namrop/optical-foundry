---
uid: 019e3736-7e10-7b10-9b1e-7d6f2a9a9d1e
kind: note
note_role: implementation-guide
validation_profile: standard
status: active
created: 2026-05-17T14:35:44-04:00
updated: 2026-05-17T14:35:44-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry — Manuscript Rendering Support Boundaries"
summary: "Documents the Foundry-owned surfaces needed to render illuminated/bound manuscripts while keeping story manifests, source text, and art assets outside core renderer documentation."
tags:
  - optical-foundry
  - manuscript-rendering
  - illuminated-initials
  - imposition
  - manifest-boundary
principal: luis
---

# Optical Foundry — Manuscript Rendering Support Boundaries

## Purpose

This guide records what Optical Foundry itself must support for illuminated or physically bound manuscript-style artifacts.

It deliberately does **not** document any one story packet, manuscript source tree, title-page art set, drop-cap image set, or editorial decision. Those belong at the artifact layer.

## Boundary: Foundry vs artifact packet

Optical Foundry owns reusable rendering capability:

- profile resolution and local profile-owned templates/styles/assets;
- PDF/LaTeX rendering through Pandoc;
- manifest compilers and projection-plan assembly;
- guarded render-resource path handling;
- source-level layout block preprocessing (`of-image`, `of-initial`);
- visual proof/contact-sheet tooling;
- post-render signature/booklet imposition;
- evidence sidecars and boundary assertions.

Artifact packets own artifact-specific content:

- the render manifest for that artifact;
- canonical or staged Markdown source text;
- chapter selection, order, front/back matter, and editorial cuts;
- specific title-page, vignette, plate, drop-cap, and other art assets;
- per-artifact tuning values such as exact initial width, line count, gap, and chapter placement;
- approval state for proof/final language.

In practical terms: Foundry should know how to render an `of-initial` block and impose a half-letter booklet. It should not carry the source Markdown or art inventory for a particular story unless that material is reduced to a generic fixture.

## Current implemented support

### 1. Foundry-owned profile runtime

The active runtime resolves defaults, templates, styles, fonts, and profile assets from the repository-local import tree:

```text
profiles/40_latex_import/
```

Current evidence should use:

- `target_legacy_profile_tree_mutated: false`
- `reads_legacy_profile_tree: false`

The external legacy profile tree is provenance/archive material, not an active fallback for normal rendering.

### 2. Source-level layout images

The `of-image` block is a source-facing, render-only layout surface for decorative images:

````markdown
```of-image
path: assets/ornaments/vignette.png
placement: wrap
align: right
width: 0.32\textwidth
edge: vignette
caption: Optional caption
```
````

Supported placements are currently `wrap`, `absolute`, `inline`, and `block`. Paths must be relative render-resource image/PDF paths; absolute paths, parent traversal, URLs, control characters, and TeX-sensitive path characters are rejected.

The preprocessor writes a generated Markdown copy under the render output directory. It does not mutate the canonical source.

### 3. Illuminated image initials

The `of-initial` block lets artwork supply the visible initial while the paragraph body remains live/selectable text:

````markdown
```of-initial
path: assets/dropcaps/example/T.png
width: .84in
lines: 4
gap: .08in
raise: 0in
align: top
```
he opening paragraph continues here without repeating the visible initial letter.
````

Generic contract:

- `path` is a guarded relative render-resource path.
- `width` is the physical rendered image width.
- `lines` is the number of text lines reserved beside the image.
- `gap` is the horizontal separation between image box and live text.
- `raise` is a small vertical correction.
- `align` is `top` or `bottom`.

Historically styled dropped initials usually want `align: top` and a fixed `lines` value so the image descends through the opening text block while normal full-width text resumes below. Ceremonial or letter-style initials may prefer `align: bottom`; this is a profile/artifact tuning decision, not a separate Foundry profile.

### 4. Asset diagnostics for transparent initials

The CLI can inspect a transparent PNG initial and report visible alpha bounds:

```bash
python3.14 -m cli initial inspect path/to/dropcap.png
```

Use this to distinguish real text-wrap problems from dead transparent canvas margin. The output includes alpha bounding box, transparent margins, crop recommendation, and crop-attention flags.

### 5. Signature/booklet imposition

After a source PDF has been rendered and validated, Foundry can impose it into booklet/signature sheet sides:

```bash
python3.14 -m cli impose input.pdf \
  --output generated/impositions/<run-name> \
  --page-size half_letter \
  --sheet-size letter \
  --signature-size 16 \
  --duplex short-edge
```

Current first-class layout: `booklet_signature_2up`, two portrait source pages per landscape sheet side. The verified production pair is half-letter pages on Letter sheets; A5-on-A4 follows the same geometric rule but should be smoke-tested before use.

The CLI emits both the imposed PDF and an `.imposition.json` page map. The page map is the audit surface for sheet/front/back page order and any padding blanks.

## What remains artifact-owned

Even with the above Foundry support, these remain outside core renderer implementation:

- which chapters receive illuminated initials;
- which initial image corresponds to each chapter;
- whether a particular artifact alternates illuminated and plain openings;
- exact title-page visible wording;
- proof/final/edition language;
- public-domain source citations for historical art;
- per-artifact art provenance and licensing packets;
- final print-stock, binding, or fulfillment decisions.

Those should live in the artifact render tree, source bundle, or artifact-specific handoff docs.

## Missing from implementation / not yet first-class

The current implementation still does **not** provide these generic Foundry capabilities:

1. **Manifest-level delivery overlay** — `render.delivery` is documented as a handoff, but not implemented. Bound/booklet behavior is not yet compiled from manifest YAML into projection-plan fields.
2. **Two-sided bound typography defaults** — mirrored inner/outer margins, outer page numbers, running-header suppression rules, and title-verso colophon behavior remain planned.
3. **Illumination rails** — outer/recto-verso ornament rails with reserved layout width are planned but not implemented.
4. **Manifest-integrated imposition** — `cli impose` works as a post-render step; manifests do not yet request imposition or include imposition output/evidence as part of a single render command.
5. **Cover/interior production split** — separate cardstock cover, title-verso treatment, and interior signature emission are not yet a typed delivery manifest output. They can be assembled manually or by artifact-local scripts.
6. **Manifest-owned exact mid-source image anchors** — exact full-page images inside body flow remain source/staged-source owned. The current manifest `figures:` lane is inventory/append oriented, not an intra-source anchor-placement system.
7. **Automated composition judgment** — Foundry can render, inspect evidence, rasterize, and make proof packets, but it does not yet decide whether an opener is aesthetically balanced. Human visual QC remains required.

## Validation checklist for manuscript-style outputs

For a generic illuminated/bound manuscript proof, validate at least:

1. Source PDF page count and every page size.
2. Evidence warnings are empty or explicitly accepted.
3. `target_legacy_profile_tree_mutated=false` and `reads_legacy_profile_tree=false`.
4. No raw macro/source block leaks in extracted text.
5. `of-initial` blocks produce live paragraph text and no repeated visible initial letter unless intentionally authored.
6. Layout image and initial paths resolve through allowed render-resource roots.
7. Visual proof pages confirm opener geometry, title-page appearance, and no clipping.
8. Imposed output page size and orientation match the printer sheet.
9. `.imposition.json` page maps match the expected signature/binding plan.
10. Artifact-specific manifest/source/art files remain outside the core Foundry repo unless they are reduced to fixtures.
