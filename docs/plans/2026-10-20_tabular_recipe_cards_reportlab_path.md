---
uid: 01a159f4-669a-73ab-9a14-45400b1b884b
kind: note
note_role: architecture_note
thinking_mode: reference
validation_profile: standard
status: active
created: 2026-10-20T11:36:55-04:00
updated: 2026-10-20T11:36:55-04:00
beam_home: docs
title: "Tabular recipe cards — structured layout to vector PDF"
summary: "Working standalone path for Cooking for Engineers-style merged-cell recipe cards: manually compose ingredient/operation spans in JSON, render vector PDFs with ReportLab, then preview, merge and verify with PyMuPDF. Two cooking-beam recipes exercised it; not integrated into Optical Foundry."
tags:
  - optical-foundry
  - recipes
  - tabular-layout
  - reportlab
  - vector-pdf
  - render-path
implementation_status: standalone_prototype
author:
  name: Lux
  harness: hermes-agent
  model: gpt-6.1-sol
  provider: openai-codex
  voyage: "hermes:session:745e1507-39ac-420c-9a1e-376024ea2279"
  at: 2026-10-20T11:36:55-04:00
last_touched:
  name: Lux
  harness: hermes-agent
  model: gpt-6.1-sol
  provider: openai-codex
  voyage: "hermes:session:745e1507-39ac-420c-9a1e-376024ea2279"
  at: 2026-10-20T11:36:55-04:00
principal: luis
related_refs:
  - uid: 01a11d76-1139-7228-8d8d-ffc35ab0f7f7
    path: docs/plans/2026-10-08_render_backend_language_annual_check.md
    relation: existing-render-backend-position
---

# Tabular recipe cards — structured layout to vector PDF

## Pith

A manually authored ingredient-and-operation grid can produce clean, selectable-text recipe cards through a small ReportLab renderer, with PyMuPDF providing previews, assembly and verification.

## Abstract

Luis brought a Short showing the Cooking for Engineers merged-cell recipe format and asked for a couple of recipes from the cooking beam in that form. The working prototype separates recipe content and explicit layout data in JSON from a Python renderer. ReportLab draws landscape Letter PDFs directly; PyMuPDF makes PNG previews, extracts text and combines the pages. The crepe and chicken-with-harissa cards exercised both a single mixture and a split-and-rejoin preparation. This note records that executable path and its local inputs, not a Foundry integration or a change to the press backend.

## Format and source

Reference: Michael Chu's [Cooking for Engineers banana nut bread](https://www.cookingforengineers.com/recipe/108/Banana-Nut-Bread), encountered through [the six-second Short](https://www.youtube.com/shorts/mbCbx1mDheg) titled “Why aren't all recipes written like this.” The video was downloaded and frame-inspected in this session.

The format encodes preparation, not just a compact ingredient list:

- Ingredients and amounts run down the left; operations progress left to right.
- Operations span the ingredient rows they act on; larger merged cells show mixtures joining.
- Ingredients can pass through empty cells until needed. Empty lanes stay separate by ingredient rather than implying premature mixing.
- A holding cell can carry a cooked component across intermediate operations before it rejoins another component.
- Setup sits above the grid. Time, temperature and sensory cues stay with their operation; variant notes stay below.

## Working implementation

Local prototype directory on Sol: `~/recipe-cards/2026-10-20/`.

| File | Role |
|---|---|
| `recipes.json` | Recipe text, source paths/UIDs, quantities, explicit geometry, spans and required text markers. |
| `render_cards.py` | Grid validation, direct vector-PDF drawing, parallel HTML generation, preview/assembly and verification. |
| `cast-iron-crepes.pdf`, `chicken-harissa-chickpeas.pdf` | Individual one-page cards. |
| `recipe-cards.pdf` | Combined two-page delivery. |
| Matching `.png` files | Raster previews made from the actual PDFs. |
| Matching `.txt` files | Text extracted from the individual PDFs. |
| `recipe-cards.html` | Parallel HTML output with `rowspan`/`colspan`; not the PDF source. Browser printing was not tested. |
| `verification.json` | Input/output hashes, page/marker results and text-fit measurements. |

The prototype remains local outside the Foundry repository. This documentation commission preserves the method and pointers; it does not copy the script, recipe data or generated artifacts into the beam.

### Input shape and composition

The top-level JSON contains `format_reference`, `trigger_video` and `recipes`.

Each recipe records:

- Identity/provenance: `id`, `title`, `subtitle`, `source_path`, `source_uid`, `source_label`.
- Page content: `setup`, `notes`, optional `companion_uid`.
- Grid: `columns`, `widths` and `heights` in PDF points; `ingredients` as one `[amount, ingredient]` pair per row.
- Operations: `steps`, each with zero-based `row` and `col`, optional `rows`/`cols` spans (default 1), `title`, `text`, and optional `join` for the pale-green operation fill.
- QA: `required_text` markers for important quantities, times, temperatures and variant distinctions.

The agent authored both the semantic mapping and the geometry. The script does not parse recipe prose into a dependency graph or automatically choose spans. In this prototype `main()` also asserts exactly two recipes and verifies a two-page combined result; another batch must deliberately update those fixed-count assertions along with the payload.

### Render sequence

1. Read the JSON and the source notes, confirm the source UIDs and hash the notes.
2. `layout_cells()` builds an occupancy grid, rejects overlapping/out-of-bounds spans, fills unused horizontal lanes and checks complete cell coverage.
3. `draw_recipe()` draws the cell rectangles on a ReportLab canvas. `Paragraph` performs wrapping and measured text-fit checks, then centers operation text vertically. The source footer carries a clickable native Atrium link.
4. Save each direct vector PDF. Page geometry is **792 × 612 points** (11 × 8.5 inches, landscape Letter), with **32-point margins** and a **728-point grid width**. Text uses Helvetica/Helvetica-Bold; the grid uses restrained green rules and fills.
5. PyMuPDF opens each saved PDF, checks geometry and required text, rasterizes it at 2× scale (**144 dpi**) for inspection, and assembles the combined PDF.
6. Recheck source hashes and write the verification sidecar. Inspect the actual PNG pages for readability, clipping and the intended dependency flow.

No diffusion/image-generation step, browser print engine, Pandoc or LaTeX is involved in this prototype. The PNGs are previews of vector PDFs, not the source artwork.

### Executed command

```sh
uv run --no-project --with reportlab --with pymupdf python ~/recipe-cards/2026-10-20/render_cards.py
```

This regenerates the working outputs beside the script. Observed isolated environment, checked while writing this note: **Python 3.11.15, ReportLab 5.0.1, PyMuPDF 2.0**. The command above leaves dependency versions unpinned; it is the command actually used, not a packaged or locked Foundry interface.

## Exercised cases and evidence

- [Cast Iron Crepes with Nutella and Whipped Cream](atrium://uid/019e50dc-1622-7622-8bac-b2a86ab8004d): batter ingredients converge at whisking, the pan joins at cooking, and toppings join only at serving. The saved base amounts remain the main card; the October doubled-sugar/doubled-butter batch remains a separate note.
- [Pan-Roasted Chicken with Harissa Chickpeas](atrium://uid/01a12d22-a6bb-7da2-aebd-2447efe23b3b): browned chicken holds on a separate track while drippings feed the onion/garlic, tomato and chickpea operations, then rejoins for roasting; parsley and lemon enter at finishing.

The successful run returned **2 individual one-page PDFs, a 2-page combined PDF, 49 text-fit checks and 24 required-text checks**, with no missing markers. Both pages were visually inspected in the originating conversation. During this documentation pass, all six output hashes in the existing sidecar matched the retained files, both source hashes still matched, and both combined-PDF page boxes were independently reopened and checked at 792 × 612 points. Original recipe notes remain unchanged.

Prototype identification, SHA-256:

```text
render_cards.py   090ff39332af218ddf074787484e771b8d76f89dcf3930b386f014c4825d4282
recipes.json      dcd2ca38204f694f7b5411127ab492e607a31feb0d00324908db28b753eae556
recipe-cards.pdf  82cb81af7d97f91650dff1933488b561a2f209f753429bd97a18a7adeeb1c709
```

These identify local prototype files, not committed Foundry source or preserved binary proofs.

## Relation to Optical Foundry

The reusable finding is the separation of **recipe meaning → explicit ingredient/operation layout → mechanical rendering → evidence and visual review**. The cooking beam owns recipe content; this beam owns the render-method record.

There is no Foundry profile, manifest subtype, compiler registration or service endpoint for this path yet. If it is integrated later, preserve that content/layout/render split and choose the Foundry-facing input and backend deliberately rather than treating the prototype JSON as an already-adopted manifest contract. The [existing render-backend position](atrium://uid/01a11d76-1139-7228-8d8d-ffc35ab0f7f7) remains a separate decision; this successful fixed-layout prototype does not reopen or replace it.

## Commission and provenance

Luis's request in this T3 Code conversation over Hermes ACP: “lets make a note in the optical foundry beam about this path to generate these recipes”. The preceding request was “pick one from the cooking beam. actually do a couple”. Session locator: `hermes:session:745e1507-39ac-420c-9a1e-376024ea2279`.

This is the commissioned record of the working method, not a new ruling adopting a renderer or commissioning its integration.
