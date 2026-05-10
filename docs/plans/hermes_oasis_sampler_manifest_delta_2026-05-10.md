---
uid: 019e1042-683c-783c-8b2d-f5ea2e9c0456
kind: note
note_role: architecture-design
validation_profile: standard
status: active
created: 2026-05-10T01:00:07-04:00
updated: 2026-05-10T01:00:07-04:00
beam_home: 42_optical_foundry_greenfield
title: "Hermes/Oasis Sampler Manifest Fidelity Delta"
summary: "Records the approved Hermes/Oasis sampler PDF path, the current YAML manifest path, and the Optical Foundry manifest-system deltas needed for faithful PDF recreation rather than approximate composite-bundle rendering."
tags:
  - optical-foundry
  - render-manifest
  - hermes
  - oasis
  - pdf-fidelity
  - delta
---

# Hermes/Oasis Sampler Manifest Fidelity Delta

## Purpose

This note captures the delta between the **approved Hermes/Oasis profile sampler PDF** and the current YAML manifest approximation made with the Optical Foundry manifest system.

The current manifest is useful as a smoke-test and provenance anchor, but it is **not yet a faithful recreation route** because the implemented `composite_bundle` compiler wraps single-source content in bundle structure.

## Approved PDF

Approved/reference PDF:

```text
~/Digital_Workspace/42_optical_foundry_greenfield/generated/hermes_oasis_profile_sampler_20260509/oasis_mythic_two_page_sampler.pdf
```

Reference source Markdown:

```text
~/Digital_Workspace/42_optical_foundry_greenfield/generated/hermes_oasis_profile_sampler_20260509/oasis_mythic_two_page_sampler.md
```

Reference evidence sidecar:

```text
~/Digital_Workspace/42_optical_foundry_greenfield/generated/hermes_oasis_profile_sampler_20260509/oasis_mythic_two_page_sampler.evidence.json
```

Important visual asset:

```text
~/Digital_Workspace/42_optical_foundry_greenfield/profiles/40_latex_import/assets/logo_oasis_2b.png
```

The approved PDF has no inline Markdown figures. The visible image comes from the `mythic` profile logo path rather than the document body.

## Current manifest

Manifest file:

```text
~/Digital_Workspace/42_optical_foundry_greenfield/manifests/hermes_oasis_profile_sampler_2026-05-09.composite-bundle.yaml
```

Committed in Optical Foundry Greenfield as:

```text
ae76989 Add Hermes Oasis sampler manifest
```

Current manifest type:

```yaml
kind: composite_bundle
schema_version: bundle_manifest_v1
profile: mythic
```

The manifest references the approved source Markdown and renders successfully through the manifest CLI, but produces a four-page approximation instead of the two-page approved PDF.

## Observed current output

Smoke render output:

```text
~/Digital_Workspace/42_optical_foundry_greenfield/generated/manifests/hermes_oasis_profile_sampler_20260509_manifest_smoke_2/hermes-oasis-profile-sampler-2026-05-09.pdf
```

Observed difference:

- approved/reference render: 2 pages;
- manifest smoke render: 4 pages;
- manifest render inserts a source wrapper heading;
- manifest render demotes source headings;
- manifest render enables section numbering;
- manifest render appends a visible `Provenance & Evidence` page;
- manifest render does not preserve all source frontmatter/Pandoc metadata behavior.

## Delta needed for faithful recreation

### 1. Single-source document manifest subtype

Add a manifest subtype for direct Markdown-document rendering, e.g. one of:

```yaml
kind: markdown_document
schema_version: document_manifest_v1
```

or:

```yaml
kind: single_source_manifest
schema_version: single_source_manifest_v1
```

This subtype should route one Markdown source through the same path as `DocumentRenderer`, not through `CompositeBundleCompiler`.

Required behavior:

- no source wrapper heading;
- no heading demotion;
- no bundle provenance page inserted into visible output;
- document frontmatter and manifest-specified metadata are merged intentionally;
- JSON evidence sidecar is still emitted.

### 2. Passthrough assembly strategy

If the same subtype is not added immediately, the bundle compiler needs an explicitly honored strategy such as:

```yaml
render:
  assembly_strategy: passthrough_single_source
```

That mode should bypass bundle assembly when there is exactly one source.

Required behavior:

- render the source body as-is;
- preserve original heading levels;
- do not inject a bundle title page or source-section page;
- do not inject visible provenance;
- still collect source inventory for evidence.

### 3. Preserve source frontmatter / Pandoc metadata

The approved source Markdown includes meaningful metadata such as:

```yaml
sample: true
toc: false
numbersections: false
```

The manifest system needs an explicit metadata merge policy.

Needed controls:

```yaml
render:
  preserve_source_metadata: true
  metadata_merge_policy: source_then_manifest_override
```

or equivalent.

Without this, the profile/template behavior can drift even when the source text and profile are correct.

### 4. Numbering control

The manifest currently carries desired intent:

```yaml
render:
  numbersections: false
```

But the current render path still invokes Pandoc with `--number-sections`.

Needed behavior:

- `numbersections: false` should map to no `--number-sections` flag;
- `numbersections: true` should map to `--number-sections`;
- absent value should fall back to profile/default behavior.

### 5. Visible provenance suppression with sidecar preservation

The current bundle compiler always appends a visible `Provenance & Evidence` page.

Needed behavior:

```yaml
render:
  emit_visible_provenance: false
  preserve_source_provenance: true
```

This should keep evidence sidecars while suppressing human-facing provenance pages for small presentation proofs.

### 6. Heading demotion control

The current bundle compiler demotes all source headings by two levels.

Needed behavior:

```yaml
render:
  preserve_source_heading_levels: true
```

or per-source:

```yaml
sources:
  - uid: oasis-mythic-two-page-sampler-source
    heading_transform: preserve
```

This matters because the approved two-page sampler’s section hierarchy is part of the visual proof.

### 7. Arbitrary profile/template variable passthrough

The manifest system should allow controlled pass-through of template variables beyond title/subtitle/author/date/toc.

Needed for this lane:

- `sample`
- `draft`
- `logo_path`
- `division`
- `tagline`
- `footeremail`
- future profile-specific fields

This should be schema-visible rather than an untyped escape hatch if the variable set becomes stable.

## Minimal implementation recommendation

The cleanest next implementation is a **document manifest subtype** rather than overloading `composite_bundle`.

Recommended small target:

```yaml
kind: markdown_document
schema_version: document_manifest_v1
profile: mythic
source:
  path: generated/hermes_oasis_profile_sampler_20260509/oasis_mythic_two_page_sampler.md
render:
  preserve_source_metadata: true
  numbersections: false
  include_toc: false
  emit_visible_provenance: false
validation:
  required_text_markers:
    - Page 1 — Oasis Mythic profile
    - Page 2 — Existing Oasis-family profiles
```

This keeps the architecture honest:

- bundles remain for multi-source assembly;
- document manifests become a reproducible YAML route for one canonical Markdown object;
- profile behavior stays profile-owned;
- evidence stays sidecar-owned.

## Status

- Approved PDF path captured.
- Current manifest path captured.
- Fidelity gap identified.
- Current approximation is runnable but not production-faithful.
- Next code work should implement the single-source/document manifest route or equivalent passthrough behavior.
