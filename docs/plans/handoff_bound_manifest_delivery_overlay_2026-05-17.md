---
uid: 019e3732-f972-7972-85a0-50413eb2d4d4
kind: note
note_role: handoff
validation_profile: standard
status: draft
created: 2026-05-17T14:31:00-04:00
updated: 2026-05-17T14:31:00-04:00
beam_home: 42_optical_foundry
title: "Handoff — Bound Manifest Delivery Overlay"
summary: "Implementation handoff for adding binding-aware delivery instrumentation to Optical Foundry render manifests without proliferating bound-specific content profiles."
tags:
  - optical-foundry
  - render-manifest
  - bound-pdf
  - delivery-mode
  - illumination
  - handoff
---

# Handoff — Bound Manifest Delivery Overlay

## Purpose

Add binding-aware PDF behavior to Optical Foundry as an overlay/instrumentation layer on top of the existing manifest system.

This should **not** create separate bound variants of content profiles such as `mythic-bound`, `keeper-bound`, or `cam-bound`. Binding behavior is a delivery/use-context concern, not a visual-identity profile concern.

## Core decision

Optical Foundry should keep this abstraction split:

- **Profile** answers: what visual/semantic identity is this artifact using?
  - Examples: `mythic`, `keeper`, `cam`, `tech`.
- **Manifest subtype** answers: what kind of render target is being declared?
  - Examples: `markdown_document`, `composite_bundle`, `cam_stack`, `codex_bundle`, `forge_packet_review`.
- **Delivery mode** answers: what physical/use context is this rendered for?
  - Examples: `screen`, `print`, `bound`, `booklet`, `saddle_stitch`.
- **Delivery overrides** answer: what does this specific artifact need?
  - Examples: mirrored margins, gutter, outer page numbering, running chapter headers, colophon behavior, illumination rail.

Compile path:

```text
render manifest
  + profile/style registry
  + delivery mode defaults
  + manifest-level delivery overrides
        ↓
ProjectionPlan / AssemblyView
        ↓
Pandoc-backed renderer
        ↓
PDF + evidence sidecars
```

## Non-goal

Do **not** solve this by adding bound-specific profiles for each content family.

Avoid:

- `mythic-bound`
- `keeper-bound`
- `cam-bound`
- `tech-bound`
- one-off profile forks whose only purpose is page geometry, headers, page numbers, or binding affordances

These rules should be composable across profile families.

## Proposed manifest surface

A concrete first-pass manifest shape could be:

```yaml
render:
  profile: mythic
  page_size: half_letter
  delivery:
    mode: bound
    binding: side_staple        # side_staple | perfect | saddle_stitch | coil | unknown
    duplex: true
    page_numbers: outer         # outer | none | center | inner | right
    running_headers:
      enabled: true
      source: chapter           # chapter | section | document_title | custom
      suppress_on:
        - title_page
        - title_verso
        - blank_pages
        - chapter_openers
    colophon:
      enabled: true
      placement: title_verso
    margins:
      inner: 0.85in
      outer: 0.60in
      top: 0.65in
      bottom: 0.70in
    illumination:
      enabled: true
      rail: outer
      width: 0.45in
      reserve_space: true
      placement: chapter_openers
      assets:
        - id: vine_gold
          source: assets/illuminations/vine_gold.svg
          pages: chapter_openers
```

The exact schema can be adjusted, but the important move is that `delivery` lives under render/instrumentation rather than replacing the existing profile/subtype model.

## Binding defaults

For `delivery.mode: bound`, default behavior should be print-safe and physically book-like:

1. **Mirrored margins**
   - Inner margin/gutter larger than outer margin.
   - Geometry should understand recto/verso or two-sided layout.

2. **Outer page numbers**
   - For bound duplex output, default page numbers should sit on the outside edge.
   - Odd/recto/right-hand pages: number on the right.
   - Even/verso/left-hand pages: number on the left.
   - This is better than a literal always-right page number because it keeps numbering away from the spine.

3. **Running headers are optional but supported**
   - Some books should have no running header.
   - Some should include chapter/section designation.
   - Default candidate: short chapter designation, e.g. `II · Where Water Remembers`.
   - Traditional option: book title on verso, chapter title on recto.

4. **Suppress headers/footers on special pages**
   - Title page.
   - Title verso / colophon.
   - Blank pages.
   - Chapter-opening pages unless explicitly overridden.
   - Full-page divider pages.

5. **Footer/contact material should move to colophon by default**
   - Avoid repeated email/contact/footer branding on every interior page for bound artifacts.
   - Put contact, copyright, generation date, edition/version, and pipeline provenance once on the title verso/colophon.

6. **Intentional blank pages**
   - Blanks inserted for recto starts/signature padding should be explicit and evidence-visible.
   - Visible text can remain the current convention: `this page was intentionally left blank`, unless profile/delivery overrides suppress visible text.

7. **Signature/page-count normalization**
   - For booklet/saddle-stitch modes, normalize to multiples of 4.
   - Future binding modes may want multiples of 8/12/16 depending the imposed signature model.
   - Do not force signature padding for ordinary perfect/side-stapled bound output unless the mode requests it.

## Margin guidance

The current manifest system already supports page size and margin overrides. Bound mode should use that capability but add semantic defaults.

Suggested first-pass defaults for half-letter or small bound books:

```yaml
margins:
  inner: 0.85in
  outer: 0.60in
  top: 0.65in
  bottom: 0.70in
```

If an outer illumination rail is enabled and `reserve_space: true`, the rail width should either:

- increase the outer margin/side decoration zone without shrinking the safe body text too aggressively, or
- compile into a separate layout variable consumed by the template so the body block and ornament rail are independently controlled.

The second route is cleaner for Optical Foundry because illumination is a layout feature, not merely a margin hack.

## Title verso / colophon rule

For bound artifacts, the title verso is the back side of the title page, usually page 2.

Use it as the default location for production metadata:

- copyright / author / steward line
- contact email or site
- edition/version
- render date
- manifest/render provenance
- typeface/toolchain note if useful
- optional short dedication/provenance line

This prevents every page from carrying footer metadata that feels like a report rather than a physical book.

## Illumination rail

Add a low-complexity illumination model based on an **outer illumination rail**.

Behavior:

- Reserve a vertical ornament rail on the edge opposite the spine.
- Recto/right-hand pages: rail appears on the right.
- Verso/left-hand pages: rail appears on the left.
- Body text stays inside the safe text block.
- Illuminations never disappear into the gutter.

Manifest controls should allow:

- enabling/disabling the rail
- rail width
- whether to reserve space even when no ornament appears
- placement policy: chapter openers, section openers, all body pages, explicit page selectors
- asset selection per chapter/section/page
- alternating recto/verso ornament variants
- suppression on frontmatter, blank pages, title pages, divider pages

Example:

```yaml
render:
  delivery:
    mode: bound
    illumination:
      enabled: true
      rail: outer
      width: 0.45in
      reserve_space: true
      placement: chapter_openers
      suppress_on:
        - title_page
        - title_verso
        - blank_pages
        - dividers
      assets:
        - id: river_vine
          source: assets/illuminations/river_vine.svg
          pages: chapter_openers
        - id: small_leaf_tailpiece
          source: assets/illuminations/small_leaf_tailpiece.svg
          pages: section_endings
```

## Implementation expectations

1. Extend the manifest contract with a `render.delivery` object.
2. Add delivery-mode defaults in the Foundry profile/render resolver without creating new content profiles.
3. Compile delivery settings into ProjectionPlan/AssemblyView fields.
4. Teach compatible LaTeX templates to consume:
   - two-sided geometry / mirrored margins
   - page-number placement strategy
   - running-header policy
   - colophon/title-verso content
   - outer illumination rail settings
5. Emit evidence sidecar fields showing:
   - effective delivery mode
   - binding mode
   - effective margins
   - page-number strategy
   - running-header policy
   - whether colophon/title verso was emitted
   - illumination rail settings and assets used
   - signature/page-count padding decisions

## Validation expectations

Bound-mode validation should check at least:

- `inner` margin is greater than or equal to `outer` when `duplex: true`.
- page numbering strategy is compatible with duplex/binding settings.
- illumination rail assets are guarded render-resource paths.
- rail width is a valid TeX dimension.
- title verso/colophon does not duplicate repeated footer metadata unless explicitly allowed.
- saddle-stitch/booklet modes produce a page count divisible by 4.
- blank/signature padding pages are represented in evidence.

## Priority implementation slice

First useful slice:

1. `render.delivery.mode: bound`
2. mirrored margins / gutter defaults
3. outer page numbers
4. suppress repeated footer/contact metadata
5. title verso colophon
6. optional running chapter headers
7. outer illumination rail with reserved width and chapter-opener placement

This is enough to make manifest-derived PDFs physically bindable without destabilizing the existing profile system.

## Open questions

- Should `bound` and `booklet` be separate modes, or should `booklet` be `mode: bound` plus `imposition: booklet`?
- Should visible intentional-blank text be suppressed by default for more book-like mythic artifacts?
- Should chapter designation be derived from heading structure, section dividers, explicit manifest metadata, or all three with precedence rules?
- Should illumination rail assets be global render resources or profile-family assets with manifest references?
- Should the rail reserve space globally for visual consistency or collapse on pages without ornament by default?

## One-line compression

Bound PDF support in Optical Foundry should be a manifest-level delivery overlay: profile identity stays separate, the manifest declares binding/geometry/header/colophon/illumination behavior, and the compiler turns those settings into a projection plan for physically bindable PDF output.
