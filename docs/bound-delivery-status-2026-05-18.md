---
uid: optical-foundry-bound-delivery-status-2026-05-18
kind: implementation_status
status: active
created: 2026-05-18
updated: 2026-05-18
beam_home: 42_optical_foundry
title: "Optical Foundry — Bound Delivery, Imposition, and Bindery Preflight Status"
summary: "Current implemented contract for manifest-owned bound delivery: mirrored margins, outer page numbers, title-verso colophon, running-header marks, manifest-owned imposition, outer/bottom illumination rails, and advisory bindery preflight/overlay proofs."
tags:
  - optical-foundry
  - render-manifest
  - bound-pdf
  - imposition
  - bindery-preflight
---

# Optical Foundry — Bound Delivery Status

## Current implementation

Optical Foundry now supports a manifest-owned `render.delivery` surface for bound prototype PDFs without creating bound-specific content profiles. Profiles remain visual/semantic identity; delivery records the physical/use-context layer.

Implemented surfaces:

- `render.delivery.mode`: `screen`, `print`, `bound`, `booklet`, or `saddle_stitch`; `booklet` and `saddle_stitch` normalize to bound delivery with saddle-stitch binding defaults.
- `render.delivery.binding`: `side_staple`, `perfect`, `saddle_stitch`, `coil`, or `unknown`.
- `render.delivery.duplex`: boolean, default true for bound output.
- `render.delivery.page_numbers`: `outer`, `none`, `center`, `inner`, or `right`; the implemented bound proof uses outer page numbers.
- `render.delivery.margins`: semantic bound margins (`inner`, `outer`, `top`, `bottom`) with half-letter/small-book defaults of `0.85in`, `0.60in`, `0.65in`, and `0.70in`.
- `render.delivery.running_headers`: optional chapter-derived marks, with suppression policy captured in evidence.
- `render.delivery.footer_metadata.suppress_repeated`: default true for bound output so repeated report footer metadata moves out of the page footer lane.
- `render.delivery.colophon`: title-verso colophon insertion, default enabled for bound output.
- `render.delivery.illumination`: chapter-opener illumination rail support, currently `outer` and optional `bottom` rails from guarded relative render-resource assets.
- `render.delivery.imposition`: manifest-owned `booklet_signature_2up` output using the existing imposition engine.

## Example manifest shape

```yaml
kind: markdown_document
profile: mythic
source:
  path: source/story.md
render:
  page_size: half_letter
  delivery:
    mode: bound
    binding: saddle_stitch
    duplex: true
    page_numbers: outer
    margins:
      inner: 0.85in
      outer: 0.60in
      top: 0.65in
      bottom: 0.70in
    running_headers:
      enabled: true
      source: chapter
    colophon:
      enabled: true
      placement: title_verso
    illumination:
      enabled: true
      rail: outer
      bottom: true
      width: 0.45in
      bottom_height: 0.30in
      bottom_offset: 0.28in
      reserve_space: true
      placement: chapter_openers
      assets:
        - id: vine_gold
          source: assets/illuminations/rail_placeholder_vine_gold.png
          pages: chapter_openers
    imposition:
      enabled: true
      layout: booklet_signature_2up
      sheet_size: letter
      signature_size: 8
      duplex: short_edge
```

## Output and evidence

A successful bound manifest render can emit, depending on options:

- primary single-page PDF;
- `.evidence.json` render evidence with delivery boundary fields;
- imposed booklet PDF;
- `.imposition.json` mapping sidecar;
- `.bindery_preflight.json` advisory press/prototype report;
- `.safe_area_guide.pdf` standalone recto/verso safe-area guide;
- `.safe_area_overlay.pdf` guide boxes overlaid on the rendered PDF.

Important evidence keys include:

- `delivery_mode`, `delivery_binding`, `delivery_duplex`, `delivery_page_numbers`;
- `delivery_margins`;
- `delivery_running_headers`, `delivery_footer_metadata`, `delivery_colophon_enabled`, `delivery_colophon_placement`;
- `delivery_illumination`, including normalized `rails`, `bottom_height`, and `bottom_offset`;
- `delivery_imposition`;
- `imposition` output metadata when requested;
- `bindery_preflight`, `safe_area_guide_path`, and safe-area overlay paths.

## Bindery preflight posture

Bindery preflight is advisory. It does not block rendering. It records whether a PDF is prototype-ready versus vendor-independent press-ready and surfaces print risks such as:

- missing bleed boxes;
- RGB images;
- low effective image PPI;
- font embedding failures;
- page-box or trim mismatches.

The current prototype lane is intended for proofing and physical inspection, not final vendor press submission. CMYK/PDF-X, real bleed boxes, richer vendor packets, and production-grade asset reports remain future work.

## Safe-area guide geometry

The safe-area guide computes recto/verso boxes from the effective trim and delivery margins:

- body text box;
- requested outer illumination rail;
- clipped safe outer illumination rail;
- optional bottom illumination rail;
- deckle/sacrificial zone;
- critical-safe region.

The overlay uses physical-page anchoring and two-pass XeLaTeX compilation so TikZ page anchors resolve before inspection. If the requested outer rail exceeds the critical-safe outer lane, the guide records both the requested rail and the clipped safe rail; the visible mismatch is a design diagnostic, not a renderer registration bug.

## Validation checkpoint

Latest observed implementation checkpoint in `~/Code/optical_foundry-dev`:

- Commit: `9ad66ef Add bottom illumination rail support` before documentation update.
- Bound delivery implementation stack includes `ebd3efe`, `d90898a`, `90f259a`, `1499be9`, `590b6ee`, `9ce6c6a`, and `9ad66ef`.
- Focused tests for delivery/imposition/preflight/illumination rails passed.
- Full regression before documentation update: `249 passed`.
- Render smoke output: `generated/bound_delivery_story_baseline_2026-05-17/bound_render_bottom_rail/`.

## Remaining work

- Per-chapter/section asset maps.
- Recto/verso asset variants.
- Explicit selector model beyond chapter openers: section openers, all body pages, page lists/ranges.
- SVG-to-bitmap/PDF conversion/cache for rail assets.
- Full-height/deckle/bleed edge-overlay mode.
- CMYK/PDF-X production lane and real bleed/trim boxes.
- Creep compensation for saddle-stitch/booklet production.
- Richer print packet export: primary PDF, imposed PDF, preflight JSON, guide PDF, vendor spec sheet, and asset report.
