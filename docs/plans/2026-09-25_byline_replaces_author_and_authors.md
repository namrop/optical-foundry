---
uid: 01a0d6fe-8c62-77f5-8ddb-72b601e8c544
kind: note
note_role: architecture_note
validation_profile: standard
status: active
created: 2026-09-25T01:19:57-04:00
updated: 2026-09-25T01:40:23-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry — byline replaces author and authors"
tags:
  - optical-foundry
  - byline
  - frontmatter
  - pandoc
  - luis-ruled
summary: "Records Luis's 2026-09-25 direction that Optical Foundry will use `byline` across the board for the credited name it prints, instead of `author` or `authors`. In Atrium frontmatter, `author` is the originating-writer block (standard §8.4) and now also carries a `principal` entry, so it cannot double as the printed name. Inventories every place Optical Foundry reads `author` or `authors` today. No code, template, schema or manifest has been changed yet."
trigger:
  initiative: luis_direct
  ratification: ratified
  summary: "Luis named the printed-name field `byline`, approved a principal entry in the author block, and asked for a note in Optical Foundry that it will need to use byline across the board instead of author or authors."
  at: 2026-09-25T01:14:41-04:00
author:
  name: Lux
  harness: hermes-agent
  model: claude-opus-5-5
  provider: custom:primary
  voyage: discord:thread:1552371356912455721
  persona: lux-prime
  principal: luis
  at: 2026-09-25T01:19:57-04:00
last_touched:
  name: Lux
  harness: hermes-agent
  model: claude-opus-5-5
  provider: custom:primary
  voyage: discord:thread:1552371356912455721
  persona: lux-prime
  principal: luis
  at: 2026-09-25T01:40:23-04:00
ruling_refs:
  - uid: 01a0d6fe-8d89-7ba1-a04f-df29dcf55b11
    relation: authorizing-ruling
  - uid: 01a0d707-948f-792d-8bcc-a552664edb53
    relation: follow-up-ruling
  - uid: 01a0d713-6c98-7ddf-9c4b-b10c60d1f210
    relation: principal-form-correction
related_refs:
  - uid: 01a08dc5-be69-7f9d-b75b-6c3e0ae524f6
    path: 20_digital_architecture/specs/atrium_frontmatter/atrium_frontmatter_standard_v2_9.md
    kind: note
    relation: frontmatter-standard-defining-author
  - uid: 01a0cfbe-be21-7b35-8fe8-f9f9ded06214
    path: 20_digital_architecture/specs/atrium_frontmatter/RULINGS.md
    kind: note
    relation: ruling-ledger
  - uid: 01a07e53-794b-7e57-953c-5f27587a95ba
    path: 20_digital_architecture/atrium_service/author_snapshot_and_writer_history_design_2026-09-07.md
    kind: note
    relation: writer-block-design
---

# Optical Foundry — byline replaces author and authors

## Pith

Optical Foundry will print a document's credited name from a field called `byline`, everywhere it now reads `author` or `authors`, because in Atrium frontmatter `author` records which writer produced a file and on whose behalf.

## Abstract

On 2026-09-25 Luis named the printed-name field `byline`, approved a `principal` entry inside the frontmatter `author` block, and asked for this note: Optical Foundry will need to use `byline` across the board instead of `author` or `authors`. Today the renderer passes frontmatter `author` to pandoc as the byline, and most of the imported LaTeX templates print pandoc's `author` variable. The frontmatter standard's `author` is a structured writer block, so the two meanings collide. This note records the direction and lists the code, templates, schemas and manifests that read `author` or `authors`. None of them has been changed yet.

## Keeper direction

Luis, 2026-09-25 01:14 EDT, in the Atrium Frontmatter thread ([1552911199795150901](https://discord.com/channels/1508563807306256496/1552371356912455721/1552911199795150901)):

> Byline is fine to call the field. Principal entry in the author block is fine. We can stamp them all at once no problem. We should write a note in the optical foundry that we will need to use byline across the board instead of author or authors.

It answered two questions put to him: whether a `principal` entry inside the writer blocks was the right shape, and what the byline field should be called. They followed his message of 01:06 EDT ([1552909104480002129](https://discord.com/channels/1508563807306256496/1552371356912455721/1552909104480002129)), which opened: "So authors is touchy, because it impacts how the optical foundry and pandoc render things. Also, technically agents wrote everything, but I am the principal for all of them."

The ruling is recorded in the frontmatter lane's ledger, `20_digital_architecture/specs/atrium_frontmatter/RULINGS.md`, entry `01a0d6fe-8d89-7ba1-a04f-df29dcf55b11`.

## Why `author` cannot stay the printed name

- In the frontmatter standard (§§8.4–8.5), `author` is a block recording the originating writer: name, harness, model, provider, voyage and time, and now the principal the write was done for. `last_touched` has the same shape for the latest writer.
- Optical Foundry's single-document path reads frontmatter `author` and hands it to pandoc as `--metadata author=…`. A writer block there would be printed as the byline. This comes from reading the code; no test render was made for this note.
- Plain-text `author` values in canon mix printed names, writer names and both (for example `Luis E. Ramirez`, `Lux`, `Luis Ramirez / Lux drafting pass`), so even where the field is plain text it is not reliably a byline.

## Where Optical Foundry reads `author` or `authors` today

Inventory taken 2026-09-25 from tracked files, with `generated/` excluded. To re-derive it: `git ls-files | grep -v '^generated/' | xargs grep -n -E '\bauthors?\b'`.

- `renderers/document_renderer.py:141`: `author=fm.get("author", "")` fills `ProjectionPlan.author` from the source file's frontmatter.
- `engine/projection_plan.py:77`: `author: str = ""`, typed as text, with no handling for a block.
- `renderers/pandoc_renderer.py:164–165`: passes `plan.author` to pandoc as `--metadata author=…` when it is set.
- `engine/manifest_compiler.py`: line 1079 prefers manifest `metadata.author` and falls back to frontmatter `author`, then lines 1134 and 1182 pass it on as text; line 1297 reads bundle `presentation.authors`, joined at lines 1582 and 1642.
- `engine/report_settings.py:61`: `author` is on the list of accepted pandoc variables.
- `engine/delivery.py:214–256`: the bound colophon takes `author` and prints it on the "Steward" line.
- `schemas/bundle_manifest_v1.yaml:60`: `authors:` in the bundle presentation block.
- `profiles/40_latex_import/templates/`: `base`, `cam`, `codex0`, `codex0_a5`, `convergence`, `keeper`, `mythic`, `generic_report`, `elian_packet` and `resume` print pandoc's `$author$` in the title block, title page or header. One further template prints it as well and also writes it into the PDF's author metadata through `author-meta`. The two `mythic_letter_johannah` templates blank it with `\author{}`.
- Manifests that set a document credit: `manifests/civic_abundance_model_v0.2_2026-05-03.document.yaml` and `manifests/hermes_oasis_profile_sampler_2026-05-09.document.yaml` (`metadata.author`), plus `presentation.authors` in the four `cam_stack_v0.2.x` meeting-packet manifests, `manifests/hermes_oasis_profile_sampler_2026-05-09.composite-bundle.yaml`, `manifests/keeper_capture_book_2026-09-01.composite-bundle.yaml`, the four bundle fixtures under `fixtures/manifests/`, and the three Codex 0 v5 build-100 bundles under `docs/delivery/build-100/`.

## Quotation credits use the same key

Codex bundle manifests also put `author:` on epigraph and quotation entries (for example `author: Hermann Hesse`). `engine/manifest_compiler.py` (lines 885–976) and `profiles/40_latex_import/filters/codex0_composition.lua:756` (`attr.author or attr.by or attr.attribution`) print it as the credit under a quotation. There it names the person quoted, not the document's credited name. They are not in frontmatter: they live in the manifests and in attributes on quotation blocks in the body. Luis ruled on 2026-09-25 that they stay as they are ([1552913771985375304](https://discord.com/channels/1508563807306256496/1552371356912455721/1552913771985375304): "Leave those alone. They’re not in the frontmatter right? Quotation credits should stay the same."). The move to `byline` covers the document’s credited name only.

## Status

- Optical Foundry code, templates, schemas and manifests are unchanged.
- The frontmatter standard does not yet define `byline` or the `principal` entry.
- The `principal` entry has not been stamped across existing files. On that, Luis said: "We can stamp them all at once no problem." The principal is written as the bare id, `principal: luis` (ruling `01a0d713-6c98-7ddf-9c4b-b10c60d1f210`, which replaced the `principal:luis` form approved minutes earlier). He asked for a dry run first, with the stamp itself run during an idle window (ruling `01a0d707-948f-792d-8bcc-a552664edb53`).
