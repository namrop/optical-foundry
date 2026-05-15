---
uid: optical-foundry-code-change-status-2026-05-12
kind: implementation_status
status: active
created: 2026-05-12
updated: 2026-05-15
title: "Optical Foundry — Code Change Status"
summary: "Code-level status for the May 2026 Optical Foundry manifest/rendering changes. This document intentionally excludes packet-specific document content notes."
tags:
  - optical-foundry
  - manifest-system
  - render-pipeline
  - code-status
---

# Optical Foundry — Code Change Status

This file records **code and contract changes only**. It should not be used as a packet-specific content log for individual CAM/Codex/meeting documents.

## Current runtime baseline

- Repository: `~/Digital_Workspace/42_optical_foundry`
- Branch: `main`
- Baseline HEAD before current uncommitted implementation slice: `ed22971c76849357cb40d4086e075856b5fe4a3c`
- Validation command: `python3.14 -m pytest -q`
- Latest observed result: `149 passed`

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
- `section_dividers` inventory with UID, kind, resolved target UID/order, pagination flags, background image path, divider-local profile evidence, and source path when applicable.
- `titlepage_blank_after`
- `section_divider_numbering`

### 3. Contract/schema/test updates

Updated implementation surfaces include:

- bundle manifest schema support for `section_dividers`, divider pagination/background/profile options, `frontmatter` source role, and divider-faithful numbering strategy;
- bundle assembly contract documentation for divider insertion order, recto/blank semantics, and frontmatter/mainmatter/appendix transitions;
- render-manifest contract documentation for generic vs source-backed divider semantics, title/divider background support, and intentional blank-page text;
- compiler tests for generic divider insertion, source-backed divider insertion, recto/title blank defaults, divider profile/background/blank-after controls, faithful numbering, template blank text, and validation failures;
- smoke evidence for title-page blank defaults, divider backgrounds, section-divider manifest behavior, and divider-faithful TOC/numbering.

### 4. Vendored `wrapfig` support for source-placed layout images

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
5. verify evidence, `pdfimages`, page count, text markers, and `target_40_latex_mutated: false`.

If exact full-page figure placement should become manifest-owned later, it needs a separate anchored-placement contract rather than overloading `figures:`.

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
