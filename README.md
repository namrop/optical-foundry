# Optical Foundry

Pandoc-backed render engine and active replacement lane for the former `40_latex` renderer. Optical Foundry now has working local runtime surfaces: profile resolution, typed render manifests, document rendering, bundle/CAM/Codex assembly, generated-figure preprocessors, title-page controls, bundle section dividers, source-level layout images/illuminated initials, manifest-owned bound delivery overlays, booklet/signature imposition, bindery preflight guides, and evidence sidecars.

`40_latex` now lives at `../08_archives/deprecated/40_latex` as the known-good behavioral reference and archive/provenance source. Normal Foundry renders resolve through the Foundry-owned `profiles/40_latex_import/` runtime surface, not an active external legacy fallback, and must not mutate legacy trees.

## Quickstart

Run from the repository root:

```bash
cd ~/Digital_Workspace/42_optical_foundry

# Render one Markdown document through a profile.
python3.14 -m cli doc path/to/source.md --profile cam --output generated/<run-name>

# Render a typed manifest: markdown_document, composite_bundle, cam_stack, codex_bundle, etc.
python3.14 -m cli manifest manifests/<manifest>.yaml --output generated/manifests/<run-name>

# Impose an already-rendered PDF into booklet/signature sheet sides.
python3.14 -m cli impose input.pdf --page-size half_letter --sheet-size letter --signature-size 16 --duplex short-edge --output generated/impositions/<run-name>

# Inspect available profiles.
python3.14 -m cli profiles

# Validate a manifest.
python3.14 -m cli validate manifests/<manifest>.yaml
```

The current validated interpreter is `python3.14`. Older examples using a hypothetical `foundry` executable or `python -m cli.render` are stale.

**Sol runtime note (2026-08-25):** on Sol the engine runs fine under the
system `python3` (3.13) with the fleet-provisioned `pandoc`/`lualatex` —
verified end-to-end with a keeper-profile render (validation passed, zero
warnings). Two follow-ups from that run:

- **DONE 2026-09-01:** the Earth-era Homebrew `.venv/` (18 MB on disk, never
  tracked — `.venv/` was already gitignored) was deleted by keeper ruling;
  recreate per-host.
- Sol lacks Helvetica/Menlo/Times New Roman, so renders fall back to
  DejaVu (recorded as declared runtime fallbacks in render evidence).
  If Sol becomes a regular render host, pin the real faces into the
  fleet environment.

## Current status

**Phase:** active local implementation / migration proving ground.

Implemented and exercised code surfaces:

- `markdown_document` render lane for single canonical Markdown objects.
- Bundle-family manifest lane: `composite_bundle`, `cam_stack`, `codex_bundle`.
- Local imported `40_latex` profile stack under `profiles/40_latex_import`.
- CAM/Yugen Civic profile rendering.
- Title pages, default blank-after-title behavior, and guarded title-page background images.
- Generated figure preprocessors for Mermaid, Vega, D2, and Graphviz/DOT.
- Source-level `of-image` and `of-initial` layout blocks, including general figure-wrap tightening controls and transparent PNG initial diagnostics.
- Evidence JSON sidecars with profile, boundary, output, source, and figure assertions.
- Bundle section dividers via top-level `section_dividers:` in bundle-family manifests.
- Manifest-owned bound delivery: mirrored margins, outer page numbers, title-verso colophon, optional running-header marks, outer/bottom illumination rails, and manifest-owned `booklet_signature_2up` imposition.
- Advisory bindery preflight sidecars plus standalone and overlaid safe-area guide PDFs for prototype inspection.

Current code-change status is tracked in:

```text
docs/IMPLEMENTATION_STATUS_2026-05-12.md
```

That status document intentionally excludes packet-specific document-content notes.

## Conceptual split

- **Markdown document:** direct Foundry input for one canonical source object.
- **Render manifest:** direct Foundry input for recurring assembled/projection cases.
- **Manifest subtype:** named contract such as `markdown_document`, `label_run`, `sticker_sheet`, `composite_bundle`, `cam_stack`, `codex_bundle`, or `forge_packet_review`.
- **Bundle:** source graph/content grouping, usually rendered through a bundle-family manifest.
- **Packet:** work/lifecycle container; rendered only through a packet-review manifest that projects packet state.
- **Projection plan / assembly view:** internal compiled render plan derived from Markdown or a manifest.
- **Rendered artifact:** PDF/DOCX/HTML output plus evidence sidecars.

## Packet and bundle presentation controls

Bundle-family manifests own assembly-level presentation between source objects:

- `presentation.title_page.*` controls packet title-page behavior.
- `generated.reader_guide` and `generated.afterword` can generate simple bundle sections where enabled.
- `section_dividers[]` inserts title/divider pages before target sources. Dividers can be generic manifest-authored pages or source-backed Markdown divider pages. Divider options include recto/right-page forcing, divider-local profile hooks, background images, blank-after insertion, and divider-faithful numbering/TOC via `render.numbering_strategy: section_dividers`.
- Manifest `figures:` is appropriate for compiler-controlled/appended figure material.

Exact mid-source full-page figure placement is still a source/staged-source concern. If exact placement should become manifest-owned, add a dedicated anchor-placement contract rather than overloading `figures:`.

## Folder map

- `profiles/` — profile registry and imported profile stack.
- `profiles/40_latex_import/` — active local defaults/templates/styles/assets imported from the known-good 40_latex profile family.
- `engine/` — manifest compilers, registry/resolver code, profile checks, generated-figure preprocessors.
- `renderers/` — Pandoc-backed document renderer.
- `schemas/` — YAML schemas for manifests and profile surfaces.
- `contracts/` — render, bundle, label, sticker, and expansion contracts.
- `cli/` — CLI entrypoint used as `python3.14 -m cli ...`.
- `validators/` — manifest validation.
- `fixtures/` — synthetic test sources/manifests.
- `tests/` — pytest suite.
- `manifests/` — user-facing and smoke manifest files.
- `generated/` — render outputs and staged generated sources; normally gitignored.
- `docs/` — implementation status and design plans.

## Core documentation

- `DESIGN.md` — architecture design plus implementation delta.
- `INDEX.md` — beam index and navigation anchors.
- `docs/IMPLEMENTATION_STATUS_2026-05-12.md` — current code-change status.
- `contracts/RENDER_MANIFESTS.md` — manifest taxonomy and runtime contract.
- `contracts/BUNDLE_ASSEMBLY.md` — bundle assembly contract, including section dividers.
- `contracts/IMPOSITION.md` — booklet/signature imposition contract and verification checklist.
- `docs/bound-delivery-status-2026-05-18.md` — implemented `render.delivery`, illumination rail, imposition, and preflight status.
- `contracts/EXPANSION.md` — adding new profiles.
- `docs/PROFILE_AND_PANDOC_REFERENCE.md` — profile/Pandoc operational notes.
- `docs/guides/figure-wraps.md` — source-level `of-image` wrapping contract and general tightening controls.
- `docs/guides/illuminated-image-initials.md` — `of-initial` asset/tuning guide.
- `docs/guides/manuscript-rendering-support-boundaries.md` — Foundry/artifact division for illuminated/bound manuscript rendering.

## Validation posture

Before reporting a render or code surface as ready, inspect the evidence JSON for `render_metadata.success`, `warnings`, page count, SHA-256, `target_legacy_profile_tree_mutated: false`, relevant title-page, section-divider, delivery, imposition, and bindery-preflight boundary assertions, and required text markers.
