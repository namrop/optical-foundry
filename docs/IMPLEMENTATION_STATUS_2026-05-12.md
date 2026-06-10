---
uid: 019eafdb-1c4c-7c4c-8b24-af1b5d4f8044
kind: note
note_role: spec
status: active
created: "2026-05-12T00:00:00-04:00"
updated: "2026-05-18T00:00:00-04:00"
title: "Optical Foundry — Code Change Status"
summary: "Code-level status for the May 2026 Optical Foundry manifest/rendering changes. This document intentionally excludes packet-specific document content notes."
tags:
  - optical-foundry
  - manifest-system
  - render-pipeline
  - code-status
validation_profile: standard
beam_home: 42_optical_foundry/docs
---

# Optical Foundry — Code Change Status

This file records **code and contract changes only**. It should not be used as a packet-specific content log for individual CAM/Codex/meeting documents.

## Current runtime baseline

- Repository: `~/Digital_Workspace/42_optical_foundry`
- Branch: `main`
- Baseline HEAD before current uncommitted implementation slice: `ed22971c76849357cb40d4086e075856b5fe4a3c`
- Validation command: `python3.14 -m pytest -q`
- Latest observed result before documentation update: `249 passed`

## Archive-readiness validation

See `docs/PROFILE_ARCHIVE_READINESS_2026-05-16.md` for the exhaustive Foundry-owned profile runtime check before archiving the external `40_latex` tree.

Current result:

- 23/23 canonical profiles covered.
- 17/17 document-compatible profiles pass basic PDF smoke.
- 17/17 document-compatible profiles pass illuminated-initial PDF smoke.
- 6/6 fixed-layout/non-prose profiles pass profile-specific PDF builds.
- 40 current evidence files parsed; no render failures, no retired evidence keys, no absolute legacy path hits, and no bad legacy boundary assertions.
- Full tests: `224 passed`.

## Implemented code surfaces

### 1. Title-page background image variables

Document and bundle-family manifests now have guarded title-page background support:

- `markdown_document` lane:
  - `variables.titlepage: true`
  - `variables.titlepage_background_image: assets/<image>.png`
- `composite_bundle` / `cam_stack` / `codex_bundle` lanes:
  - `presentation.title_page.enabled: true`
  - `presentation.title_page.background_image: assets/<image>.png`
  - `presentation.title_page.blank_after: false` only when suppressing the default intentional blank page after the title page.

Security boundary:

- accepted path values must be relative render-resource image paths;
- absolute paths, URLs, parent traversal, unsafe extensions, non-scalar values, and LaTeX-control/injection tokens are rejected;
- direct Markdown frontmatter is normalized before Pandoc so unsafe title-page background variables do not leak through.

Evidence boundary fields include:

- `title_page_background_enabled`
- `titlepage_background_image`
- `accepted_title_page_variables`
- `rejected_title_page_variables`

### 2. Bundle `section_dividers` manifest surface

Bundle-family manifests now support top-level `section_dividers:` for inserting intentional section-title pages before a target source.

Supported target selectors:

- `before_source_uid`
- `before_source_order`

Supported divider forms:

- generic divider, rendered from manifest fields:
  - `title`
  - optional `subtitle`
  - optional `body`
- source-backed divider, rendered from an arbitrary Markdown file:
  - `source.path`
  - `source.include_frontmatter: full | summary | none`

Compiler behavior:

- dividers are inserted into the assembled Markdown immediately before the targeted source;
- dividers default to recto/right-page opening (`force_right_page: true`), inserting labeled intentional blanks as needed;
- `blank_after: true` adds a labeled intentional blank page after a divider; default is false;
- `background_image` attaches a full-page background to the divider page using the guarded render-resource path rules;
- `profile_id` / `profile_family` resolve a divider-local profile hook for compatible templates and evidence;
- source-level and divider-level `running_text` overrides can change section-local header/footer text without changing profile assets or geometry;
- `render.numbering_strategy: section_dividers` makes divider titles own numbered top-level sections, demotes following source headings one level, emits frontmatter/mainmatter/appendix transitions, and reflects the resulting structure through memoir/Pandoc TOC numbering;
- `AssemblyView.generated_sections` records `section_divider:<uid>` entries;
- generic divider text is LaTeX-escaped;
- source-backed dividers use a page boundary before and after the source body;
- canonical source files remain untouched.

Validation behavior:

- duplicate divider UIDs are rejected;
- missing target sources are rejected;
- source-backed divider paths must exist;
- `include_frontmatter` must be one of `full`, `summary`, or `none`;
- generic dividers require `title`.

Evidence boundary fields include:

- `section_dividers_enabled`
- `section_divider_count`
- `section_dividers` inventory with UID, kind, resolved target UID/order, pagination flags, background image path, divider-local profile evidence, divider-local `running_text`, and source path when applicable.
- `source_running_text_overrides` inventory for per-source header/footer text overrides.
- `titlepage_blank_after`
- `section_divider_numbering`

### 3. Contract/schema/test updates

Updated implementation surfaces include:

- bundle manifest schema support for `section_dividers`, divider pagination/background/profile options, per-source/per-divider `running_text`, `frontmatter` source role, and divider-faithful numbering strategy;
- bundle assembly contract documentation for divider insertion order, recto/blank semantics, and frontmatter/mainmatter/appendix transitions;
- render-manifest contract documentation for generic vs source-backed divider semantics, title/divider background support, and intentional blank-page text;
- compiler tests for generic divider insertion, source-backed divider insertion, recto/title blank defaults, divider profile/background/blank-after controls, faithful numbering, template blank text, and validation failures;
- smoke evidence for title-page blank defaults, divider backgrounds, section-divider manifest behavior, and divider-faithful TOC/numbering.

### 4. Foundry-owned profile runtime imports

Optical Foundry no longer uses the external legacy profile tree as an active runtime fallback. The renderer and profile checker resolve defaults, templates, styles, and profile assets through the Foundry-owned import tree:

```text
profiles/40_latex_import/
  defaults/
  templates/
  assets/
  styles/texmf/
```

Runtime behavior:

- missing defaults/templates are reported as `missing`, not silently loaded from the external legacy tree;
- `TEXINPUTS`, `TEXMFHOME`, Pandoc `--resource-path`, and profile asset roots are built from the Foundry-owned import surface plus the repo root;
- explicit relative template overrides resolve only under `profiles/40_latex_import/templates/`;
- profile capability JSON reports `uses_legacy_profile_tree: false` for all profiles;
- render/profile evidence uses `target_legacy_profile_tree_mutated: false` and `reads_legacy_profile_tree: false`.

Validation guardrails:

- runtime code under `engine/`, `renderers/`, and `cli/` is tested against absolute references to `~/Digital_Workspace/40_latex`;
- profile summaries require local defaults/templates for all currently resolved profiles;
- generated smoke evidence must not contain legacy profile-tree boundary keys.

### 5. Vendored `wrapfig` support for source-placed layout images

The local imported TeX tree now vendors CTAN `wrapfig.sty` under:

```text
profiles/40_latex_import/styles/texmf/tex/latex/generic/wrapfig.sty
```

This makes `of-image` blocks using `placement: wrap` resolve through the
profile-owned `TEXINPUTS` path instead of silently depending on the host TeX
installation. The `wrapfig` package remains covered by the LaTeX Project Public
License as noted in the upstream package header.

Regression coverage verifies that `kpsewhich wrapfig.sty` resolves to the local
Optical Foundry import tree when run with the resolved profile environment.

Layout-image preprocessing also now injects render-only `\graphicspath` roots
for the source directory and render output directory. This lets relative
`of-image` paths such as `assets/foo.png` resolve from staged source packets
without requiring authors to hand-insert LaTeX path plumbing.

## Full-page image placement boundary

Use the manifest for full-page images only when the image is part of a **compiler-owned presentation surface**:

- title page background image;
- source-backed section-divider page;
- generic section divider page with no image unless the divider source file supplies it.

Do **not** rely on the current manifest `figures:` lane for exact full-page, mid-source image placement. That lane is inventory/append oriented and does not yet encode semantic anchors inside a source body.

For exact intra-source full-page figures, the current safe boundary is:

1. keep canonical source untouched;
2. create a generated/staged source copy;
3. insert the full-page image block at the semantic anchor inside that staged source;
4. render the staged source through the manifest;
5. verify evidence, `pdfimages`, page count, text markers, and `target_legacy_profile_tree_mutated: false`.

If exact full-page figure placement should become manifest-owned later, it needs a separate anchored-placement contract rather than overloading `figures:`.

### 6. Source-level layout images and illuminated initials

Optical Foundry supports source-authored decorative layout blocks that lower into guarded render-only LaTeX while preserving canonical Markdown sources:

- `of-image` supports `wrap`, `absolute`, `inline`, and `block` placements with guarded relative image/PDF paths, safe dimensions, opacity bounds, and optional soft/vignette edge treatment.
- `of-initial` supports transparent image initials with `path`, `width`, `lines`, `gap`, `raise`, `align`, and optional named recipes. The following paragraph remains live text and should not repeat the visible initial letter.
- The preprocessor writes generated Markdown under the render output directory and injects `\graphicspath` roots for the source directory and output directory so staged-source art can resolve without mutating canonical source.
- CTAN `wrapfig.sty` and `yugenillumination.sty` resolve through the Foundry-owned TeX import tree.
- `python3.14 -m cli initial inspect <png>` reports transparent PNG alpha bounds/crop guidance for drop-cap spacing diagnosis; `python3.14 -m cli initial recipes` lists named initial recipes.

For generic manuscript-style outputs, the artifact source chooses chapter placement and exact tuning values; Foundry only owns the reusable block contract, preprocessing, path safety, and evidence inventory.

### 7. Booklet/signature imposition CLI

Optical Foundry now has a post-render imposition lane:

```bash
python3.14 -m cli impose input.pdf \
  --output generated/impositions/<run-name> \
  --page-size half_letter \
  --sheet-size letter \
  --signature-size 16 \
  --duplex short-edge
```

Implemented behavior:

- layout: `booklet_signature_2up`;
- validates input PDF page size before imposing;
- emits two portrait source pages per landscape sheet side;
- pads final signatures with blank slots when needed;
- writes an imposed PDF plus `.imposition.json` page-map evidence;
- verifies the imposed output sheet size/orientation.

This lane is now also callable from manifest-owned `render.delivery.imposition` for bound/booklet outputs. The standalone CLI remains useful for already-rendered PDFs. See `contracts/IMPOSITION.md`.

### 8. Foundry/artifact division for manuscript rendering

The renderer documentation now records the line between generic Foundry support and artifact-specific packet material in `docs/guides/manuscript-rendering-support-boundaries.md`.

Foundry owns reusable support for profiles, manifests, source layout block preprocessing, path safety, evidence, proof tooling, and imposition. Artifact packets own their manifest, Markdown source text, exact art inventory, chapter/drop-cap choices, edition/proof wording, and approval state.

### 9. Manifest-owned bound delivery, imposition, preflight, and illumination rails

`render.delivery` is implemented as the physical/use-context overlay for bound PDFs without adding bound-specific content profiles.

Implemented behavior:

- delivery normalization for `mode: bound` plus `booklet` / `saddle_stitch` aliases;
- semantic bound margins, two-sided/mirrored geometry variables, outer page numbers, repeated-footer suppression, title-verso colophon insertion, and optional chapter-derived running-header marks;
- guarded illumination rail assets for chapter openers, including outer rail and optional bottom rail placement;
- manifest-owned `booklet_signature_2up` imposition using the existing imposition engine;
- advisory bindery preflight JSON plus standalone and overlaid safe-area guide PDFs;
- safe-area guide geometry that distinguishes requested outer rail width from the clipped critical-safe rail box and records bottom rail boxes.

Documentation anchor: `docs/bound-delivery-status-2026-05-18.md`.

Latest observed validation before documentation update:

- Focused delivery/imposition/preflight/illumination tests passed.
- Full regression: `249 passed`.
- Bound proof smoke output: `generated/bound_delivery_story_baseline_2026-05-17/bound_render_bottom_rail/`.

Remaining production gaps: CMYK/PDF-X, real bleed/trim boxes, creep compensation, richer vendor packets, per-chapter asset maps, recto/verso ornament variants, selector model beyond chapter openers, and dedicated SVG-to-bitmap/PDF asset conversion/cache.

## Roadmap — next code surfaces

### 1. `--format docx` CLI adapter

The CLI currently renders only to PDF. DOCX output is possible via a manual workaround (compile manifest → strip LaTeX-only commands → Pandoc direct), but there is no first-class `python3.14 -m cli manifest <manifest.yaml> --format docx` path.

What it needs:

- a `format` / `output_format` argument on `cmd_manifest` and `cmd_doc` that is not just `--output` directory naming;
- a Pandoc render path that targets `--to docx` instead of `--to pdf` through `--pdf-engine xelatex`;
- evidence sidecars appropriate to DOCX output — media count, zip-internal markers, raw-LaTeX leakage check — instead of PDF-only fields;
- DOCX-safe preprocessing for source-backed dividers and body figures that currently emit raw `\includegraphics` or `\begin{figure}` blocks;
- tests for DOCX-path detection, evidence shape, and LaTeX-stripping correctness without requiring a full DOCX file.

Tracking label: `of-docx-cli-adapter`

### 2. Render-only emoji image substitution

Some source documents use emoji or Unicode status glyphs as semantic markers. Font fallback is not a sufficient production strategy: XeLaTeX can drop glyphs when the active text font lacks coverage, while LuaLaTeX may succeed only by depending on host-installed emoji fonts. The Foundry needs a render-only substitution layer that preserves Markdown source exactly while lowering selected emoji clusters to vendored image assets during PDF projection.

What it needs:

- a small, explicit emoji asset registry seeded from Noto Emoji assets, with per-glyph provenance and a later Oasis-native override lane;
- render-only source rewriting for PDF/LaTeX profiles that normalizes equivalent clusters such as `⚠` and `⚠️` to the same asset key;
- raw-LaTeX inline image output using `graphicx`, with stable sizing/raise defaults and no source mutation;
- guardrails that avoid rewriting fenced code blocks and inline code spans;
- render evidence fields for policy, source asset family, substituted counts, asset paths, and whether host emoji fonts are required;
- a smoke target against `20_digital_architecture/atrium_cleanup_sweep/evidence/atrium_root_beam_directory_tree_2026-05-24.md` proving zero missing-character warnings for `⚠️` under the existing keeper/XeLaTeX path.

Tracking label: `of-render-only-emoji-assets`

### 3. LuaLaTeX migration assessment

LuaLaTeX already works for several profile families and can render color emoji through host fonts, but switching all profiles from XeLaTeX is a layout and implementation migration rather than a one-line fix. XeLaTeX remains the current stability baseline for several defaults and for hard-coded preflight/imposition paths.

What it needs:

- inventory and classify all profile defaults by engine: safe to switch, needs visual regression, or should remain XeLaTeX;
- replace hard-coded XeLaTeX invocations in bindery preflight and imposition with the same engine-resolution policy used by document rendering;
- update tests that currently skip only on XeLaTeX availability;
- broad smoke renders comparing page count, warnings, fonts, and text extraction across representative profiles;
- explicit policy that emoji correctness is handled by vendored render assets, not by assuming LuaLaTeX host emoji-font fallback.

Tracking label: `of-lualatex-migration-assessment`

## Known bugs

### composite_bundle TOC is broken with duplicate h1 headings from combined_markdown assembly (2026-05-27)

A `composite_bundle` manifest using `render.assembly_strategy: combined_markdown` and `render.include_toc: true` produces a broken table of contents: the Contents page renders a heading and page number but contains no valid entries — only a bare page number. Reproduced with the `tech` profile on `main` (ba79f3b).

**Root cause (confirmed 2026-05-27):** The combined markdown intermediate contains **duplicate `# h1` headings** for each source — one injected by the bundle compiler as a section wrapper (preceded by `\newpage`), and one preserved from the source file's own `# h1`. With 6 blog posts, this produces 12 h1 headings (6 unique titles × 2) plus a trailing "Provenance & Evidence" h1. Pandoc's `--toc --toc-depth 1` cannot construct a valid TOC from this duplicate-heading structure. The evidence confirms `suppress_source_wrapper_headings: False` — the duplication is by design but the TOC machinery fails to handle it.

**Workaround:** Set `render.include_toc: false`. Single-document renders (`markdown_document` / `cli doc`) with TOC work correctly because they have no injected wrapper headings.

**Possible fix:** Setting `suppress_source_wrapper_headings: true` would eliminate the duplicates by suppressing the compiler's injected section headings, leaving only the source's own h1s for the TOC. Alternatively, the compiler could strip source h1s when it knows it's injecting wrapper headings for the same content.

**Tracking label:** `of-combined-markdown-toc`
