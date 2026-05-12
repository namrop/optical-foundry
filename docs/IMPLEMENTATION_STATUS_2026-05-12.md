---
uid: optical-foundry-code-change-status-2026-05-12
kind: implementation_status
status: active
created: 2026-05-12
updated: 2026-05-12
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
  - `presentation.title_page.blank_after: true` when an intentional blank page should follow the title page.

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
- `section_dividers` inventory with UID, kind, resolved target UID/order, and source path when applicable.

### 3. Contract/schema/test updates

Updated implementation surfaces include:

- bundle manifest schema support for `section_dividers`;
- bundle assembly contract documentation for divider insertion order;
- render-manifest contract documentation for generic vs source-backed divider semantics;
- compiler tests for generic divider insertion, source-backed divider insertion, and validation failures;
- smoke evidence for title-page background and section-divider manifest behavior.

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
