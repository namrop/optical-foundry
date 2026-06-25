---
uid: 019df61e-0a36-7a36-8c6e-7be50140094b
kind: note
note_role: contract
validation_profile: standard
status: active
created: 2026-05-04T23:15:00-04:00
updated: 2026-05-12T02:07:45-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry — Render Manifest Contract"
summary: "Defines render manifests as the primary non-Markdown input to Optical Foundry, with typed subtypes for packets, bundles, labels, stickers, CAM Stack, Codex 0, and other recurring render targets."
tags:
  - optical-foundry
  - render-manifest
  - architecture
  - contract
---

# Optical Foundry — Render Manifest Contract

## Decision

Optical Foundry accepts two stable input classes:

1. Markdown documents.
2. Render manifest files.

A Markdown document is the direct path for rendering one source object. A
`markdown_document` manifest is the typed, YAML-controlled path for rendering one
canonical Markdown object while preserving direct-document semantics. Bundle,
packet, physical-sheet, CAM Stack, Codex, and similar manifests are the path for
assembled, multi-source, physical-layout-based, or lifecycle-state projections.

## Manifest role

A manifest is the **render target declaration**. It says what should be rendered,
which subtype contract applies, what source/state object is referenced, which
profile/style should be used, and what validation/evidence should be emitted.

Document and bundle manifests may also carry bounded presentation controls that
are explicitly part of the render surface, not source truth. For bundle section
breaks:

- `bundle_manifest_v1.section_dividers[]` inserts a section-title/divider page
  before a selected bundle source.
- A generic divider uses manifest text fields (`title`, `subtitle`, `body`) and
  is rendered as a basic full-page section break.
- A source-backed divider uses `source.path` to render a Markdown object as the
  divider page. This is the right lane when the section title page is a designed
  object rather than a simple generated heading.
- Divider pagination defaults to recto/right-page opening (`force_right_page: true`).
  Inserted blank pages use the explicit text `this page was intentionally left blank`.
- Dividers may set `profile_id` / `profile_family` for profile-aware divider
  styling/evidence and `background_image` for a full-page divider background.
- `blank_after: true` inserts an intentional blank page after a divider; default
  is false for section dividers.
- `render.numbering_strategy: section_dividers` makes dividers own numbered
  top-level sections, demotes source headings below their divider, emits
  frontmatter/mainmatter/appendix transitions, and lets the memoir/Pandoc TOC
  reflect that section structure.

For single-document matter designation:

- `markdown_document.source.role: frontmatter` emits a memoir `\\frontmatter`
  command before the source body while preserving faithful single-document
  semantics.
- The direct Markdown document path also honors source YAML frontmatter fields
  `role: frontmatter`, `document_role: frontmatter`, `render_role: frontmatter`,
  or `matter: frontmatter`.
- This exists for parity and emergency use. If a document has meaningful front
  matter/main matter structure, the durable lane is usually a manifest, because
  the manifest can make ordering, transitions, validation, and evidence explicit.

For page size and margins:

- `markdown_document.render.page_size` supports `letter` (default), `a4`, `a5`,
  and `half_letter`/`half-letter`/`half letter`/`statement`.
- The direct Markdown document path also honors source YAML frontmatter
  `page_size` / `page-size` / `papersize` for the same supported values.
- Bundle-family manifests (`composite_bundle`, `cam_stack`, `codex_bundle`) use
  `render.page_size` with the same supported values.
- Page-size overrides are scoped to document-spine PDF/LaTeX profiles. Letter,
  stationery, labels, stickers, resume, and campaign-art templates retain their
  paper assumptions unless they move onto a document-spine profile path.
- Optional margin overrides are `render.margin` / source-frontmatter
  `page_margin` for a uniform margin, or `render.margins` for side-specific
  `top`, `bottom`, `left`, `right`, `inner`, `outer`, `hmargin`, `vmargin` values.
  Values must be plain TeX dimensions such as `0.7in` or `18mm`; omission
  preserves the active profile's default margin.
- Page-size and margin overrides are PDF/LaTeX geometry overrides. They are
  reliable for document-spine profiles/templates that consume Pandoc `geometry`
  variables. Non-PDF outputs and physical sheet specs remain separate lanes.
- Physical booklet/signature imposition is available both as the standalone
  `python3.14 -m cli impose ...` command and as a manifest-owned delivery output
  through `render.delivery.imposition` for bound/booklet-style PDF renders.

For title pages:

- `markdown_document.variables.titlepage: true` enables the full title-page path
  for compatible LaTeX templates.
- `markdown_document.variables.titlepage_background_image: assets/path.png` sets
  a full-page image background for that title page.
- `bundle_manifest_v1.presentation.title_page.background_image: assets/path.png`
  sets the same title-page background for bundle-family manifests and implicitly
  enables the full title-page path unless `enabled: false` is set.
- `bundle_manifest_v1.presentation.title_page.blank_after` defaults to true for
  enabled full title pages. The inserted page is labeled
  `this page was intentionally left blank`.

Title-page image paths are guarded render-resource paths: relative PNG/JPG/PDF
paths only, no absolute paths, parent traversal, URLs, or LaTeX control-token
injection.

## Bound delivery surface

`render.delivery` is the manifest-owned physical/use-context layer. It must not
be modeled as bound-specific profile forks. The current implemented bound lane
supports:

- `mode`: `bound`; aliases `booklet` and `saddle_stitch` normalize into bound
  delivery with saddle-stitch defaults.
- `binding`: `side_staple`, `perfect`, `saddle_stitch`, `coil`, or `unknown`.
- `duplex`: boolean.
- `page_numbers`: `outer`, `none`, `center`, `inner`, or `right`.
- `margins`: semantic bound margins `inner`, `outer`, `top`, `bottom`.
- `running_headers`: optional chapter-derived marks and suppression policy.
- `footer_metadata.suppress_repeated`: default true for bound output.
- `colophon`: currently title-verso colophon insertion.
- `illumination`: guarded relative render-resource assets for chapter-opener
  outer rails and optional bottom rails. Bound illumination also injects a
  generic `\OFEdgeOrnament[key=value]{asset}` LaTeX primitive for explicit
  edge/corner ornaments. The first physical-proof behavior anchors outer-edge
  ornaments to the critical-safe outer rail edge (`0.25in` inside trim), using
  the same rail width, top margin, and verso/recto page routing as the
  illumination rail header path.
- `imposition`: optional manifest-owned `booklet_signature_2up` output with
  `sheet_size`, `signature_size`, and `duplex` controls.

A bound manifest render may emit the primary PDF, an imposed PDF plus
`.imposition.json`, advisory `.bindery_preflight.json`, and safe-area guide PDFs.
Preflight is advisory and does not block render success.

A manifest may point to:

- a bundle/source graph;
- a Forge packet or other lifecycle container;
- a label run;
- a sticker sheet;
- CAM Stack;
- Codex 0;
- another recurring artifact family that earns a named subtype.

## Subtype rule

Create a manifest subtype when a render target recurs enough to deserve its own
contract, compiler, validation rules, or generated sections.

Use a generic composite/bundle manifest for one-off assembled renders. Promote to
a named subtype when the same artifact family starts recurring.

Current expected subtypes:

| Manifest kind | Purpose |
|---|---|
| `markdown_document` | Faithful YAML-controlled render of one canonical Markdown source; no wrapper headings, heading demotion, or visible provenance by default. |
| `label_run` | Physical label-sheet render from label sources and sheet spec. |
| `sticker_sheet` | Sticker-sheet render from cells/assets/layout declarations. |
| `composite_bundle` | Generic multi-source bundle render. |
| `cam_stack` | CAM Stack recurring bundle/artifact contract. |
| `codex_bundle` | Codex 0 source bundle/artifact contract. |
| `forge_packet_review` | Projection of Forge packet lifecycle state for review. |

## Packet vs bundle example: Codex 0

There may be a Forge packet whose job is to assemble the Codex 0 bundle. That
packet owns work governance: goal, constraints, plan, questions, progress,
validation, and evidence.

The Codex 0 bundle manifest owns the source artifact assembly: source files,
order, roles, generated front/back matter, profile, and validation expectations.

The same Forge packet may also have a packet-review manifest that renders packet
state for review. That is a different render target from the Codex 0 source
bundle.

```text
Codex 0 Forge packet
  ├── governs work to assemble/update Codex 0
  ├── owns/updates codex_bundle manifest + source set
  └── may expose forge_packet_review manifest for packet-state review

codex_bundle manifest → Codex 0 artifact
forge_packet_review manifest → packet-state review artifact
```

## Compiler boundary

Optical Foundry should compile every manifest into an internal projection plan /
assembly view before rendering:

```text
Markdown document OR render manifest
        ↓
compiler for input/subtype
        ↓
ProjectionPlan / AssemblyView
        ↓
Pandoc-backed renderer
        ↓
Rendered artifact + evidence
```

The renderer should not need to know whether the projection came from a bundle, a
packet, a label run, or Codex 0. Subtype-specific logic belongs in manifest
compilers and validators.
