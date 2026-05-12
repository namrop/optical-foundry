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

For title pages:

- `markdown_document.variables.titlepage: true` enables the full title-page path
  for compatible LaTeX templates.
- `markdown_document.variables.titlepage_background_image: assets/path.png` sets
  a full-page image background for that title page.
- `bundle_manifest_v1.presentation.title_page.background_image: assets/path.png`
  sets the same title-page background for bundle-family manifests and implicitly
  enables the full title-page path unless `enabled: false` is set.

Title-page image paths are guarded render-resource paths: relative PNG/JPG/PDF
paths only, no absolute paths, parent traversal, URLs, or LaTeX control-token
injection.

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
