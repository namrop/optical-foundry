---
uid: 01a0f89a-4d3d-7a47-8006-9deab5792bfc
kind: note
note_role: glossary
validation_profile: standard
status: draft
created: 2026-10-01T13:55:00-04:00
updated: 2026-10-01T16:45:00-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry glossary — the domain language"
summary: "The Foundry's domain language: one canonical word per concept, with the words to avoid. Started 2026-10-01 at the keeper's request ('we should make a GLOSSARY.md file as well') alongside the first improve-codebase-architecture review, in the format of the domain-modeling skill (mattpocock/skills v1.3): terms only, no implementation detail. Drawn from DESIGN.md, the plan notes and RULINGS.md; where those use two words for one thing, the pick is proposed and open to the keeper. Updated inline as terms are settled."
tags:
  - optical-foundry
  - glossary
  - domain-language
author:
  name: Claude Opus 5.5
  harness: hermes-agent
  model: claude-opus-5-5
  provider: custom:primary
  voyage: "t3-code:hermes-acp"
  at: 2026-10-01T13:55:00-04:00
last_touched:
  name: Claude Opus 5.5
  harness: hermes-agent
  model: claude-opus-5-5
  provider: custom:primary
  voyage: "t3-code:hermes-acp"
  at: 2026-10-01T13:55:00-04:00
principal: luis
---

# Optical Foundry

The engine that turns Atrium Markdown into printed and printable artifacts. It is releasable on its own; the works it renders and the profiles they are set in are inputs to it, not parts of it.

## Pith

One word per Foundry concept, and the words not to use for it.

## Abstract

This is the Foundry's domain language, in the format the improve-codebase-architecture and domain-modeling skills expect: short definitions of what each thing is, grouped by area, with an *Avoid* line where the repository has used competing words. It holds no implementation detail; how a thing is built belongs in `DESIGN.md` and the plan notes, and why it was decided belongs in `RULINGS.md`. Terms here are drafts until the keeper settles them; an *Avoid* line marked *(proposed)* is a pick between words the repo already uses, not a ruling.

## Language

### What goes in

**Source**:
One Markdown document, Atrium context object or otherwise, given to the Foundry as content.
_Avoid_: input file, note (when the role in a render is meant)

**Work**:
A body of content that owns its own sources and assets and is rendered as one or more artifacts; Codex 0 and the keeper-capture book are works.
_Avoid_: book (for the general concept), tenant (for the content itself) *(proposed)*

**Asset**:
A non-text file a work or profile supplies to a render, such as a plate, ornament or logo. Assets are content, never engine.
_Avoid_: resource (for the file itself)

**Manifest**:
The authoritative declaration of what to render: which sources, in what order, set in which profile, delivered how. Anything more structured than one source is rendered from a manifest.
_Avoid_: spine, bundle file, config

**Manifest kind**:
The family a manifest belongs to, which decides how it is read: a single document, a bundle, a label run, a sticker sheet, and their named subtypes.
_Avoid_: manifest type, mode

**Bundle**:
An ordered group of sources rendered as one artifact, with dividers and front and back matter. A bundle is content grouping, not a work in progress.
_Avoid_: packet, stack (except in the CAM Stack's own name)

**Selection**:
A short declaration of which sources a manifest should contain, by folder, field and date, from which the manifest is composed. The manifest it produces is the record; the selection is how it was made.
_Avoid_: query, spine

**Spine**:
Codex 0's own hand-authored ordering of parts, chapters and passages. Book data, not a Foundry concept; the Foundry's direction is for manifests to make it unnecessary.
_Avoid_: using it for any work other than Codex 0

### How it is set

**Profile**:
A named, self-contained way of setting content: its defaults, template, styles and filters. Profiles are configuration the engine loads, not engine code.
_Avoid_: theme, style, layout

**Profile family**:
The class of output a profile produces, such as a document spine, stationery, a label sheet or a sticker sheet. It decides which render options apply.
_Avoid_: profile type, output class

**Document spine**:
The profile family for flowing prose documents. Unrelated to Codex 0's spine.
_Avoid_: shortening it to "spine"

**Reference implementation**:
The profile whose mechanisms the others are measured against and from which general mechanisms are promoted into the engine; codex0 holds this role.
_Avoid_: the outlier, the special case

### Structure inside an artifact

**Divider**:
A page or page group that opens a section of a bundle, carrying its title and optionally art.
_Avoid_: section page, part page, title card

**Chapter opener**:
The heading block that begins one source in a bundle, carrying its title and optionally an epigraph.
_Avoid_: wrapper heading

**Plate**:
A full-page image. A divider plate belongs to a divider; a floating plate is placed near a point in the prose on the first page the layout allows.
_Avoid_: figure, full-page image, illustration (for the page)

**Edition**:
One reader-specific version of a work, selected at render time from the same sources.
_Avoid_: variant, version

**Register**:
The voice a passage is set in, which changes how it is typeset.
_Avoid_: style, tone

**Glyph substitute**:
A stand-in the Foundry supplies for a character the profile's fonts lack: an image for an emoji, or a small fallback font for script and symbol characters, which stay text.
_Avoid_: emoji asset (for the general concept), font fallback (for the engine's Helvetica-to-DejaVu substitution, which is a different thing)

### Making the artifact

**Render**:
One run of the Foundry from a source or manifest to an artifact and its evidence.
_Avoid_: build (for a single run), compile

**Render mode**:
Whether a render is full, measure (only measured by a later step) or draft (images as empty boxes). Only a full render is a deliverable.
_Avoid_: preview, proof (for the mode)

**Build**:
A work's multi-render production run that ends in deliverable artifacts, numbered in the work's build ledger.
_Avoid_: render (for the whole run)

**Resource root**:
A folder the Foundry searches for a referenced asset, in fixed order of precedence: the render's own output, the source's folder, the work's declared roots, then the profile.
_Avoid_: search path, asset folder

**Evidence**:
The machine-readable record written beside every artifact: what was rendered, from what, how, and with which files.
_Avoid_: log, metadata, report

**Artifact**:
What a render produces for people: a PDF, with its text layer and evidence beside it.
_Avoid_: output (when the reader-facing thing is meant)

### Physical object

**Delivery**:
How an artifact is meant to be used physically, such as read on screen or bound, which decides margins, folios and furniture.
_Avoid_: output mode, print mode

**Signature**:
A group of pages printed on folded sheets and bound together as one unit.
_Avoid_: gathering, quire, booklet

**Imposition**:
The arrangement of an artifact's pages onto printer sheets so that folding puts them in reading order.
_Avoid_: layout, booklet printing

**Bind shape**:
An artifact padded to a whole number of signatures, ready to impose.
_Avoid_: padded PDF

**Build stamp**:
The line in a bound artifact naming the build and the source state it was made from.
_Avoid_: version string, watermark

**Volume**:
One physically bound part of a work that is too long to bind as one; the work's folios run on unbroken from one volume to the next.
_Avoid_: book (for one volume of a work), part

**Folio**:
A page's number in the work's sequence, as its PDF page label records it, whether or not the page prints it.
_Avoid_: page number (ambiguous with the physical page), printed number

**Seat**:
To start a volume's body at a given folio, on the physical side that folio's parity requires.
_Avoid_: offset, restart numbering

**Contents of the Work**:
The list, in every volume, of the work's dividers with their volumes and folios.
_Avoid_: master index, combined TOC

### Checking

**Regression run**:
A whole-work render made only to be compared with another, which claims no build number and changes nothing in the work.
_Avoid_: test build, dry run

**Contact sheet**:
One image holding small renderings of every page of an artifact, used to compare two runs at a glance.
_Avoid_: thumbnail grid, page overview

**Marked page**:
A page that differs between two runs only in a way the keeper has accepted, reported as accepted rather than passed or failed.
_Avoid_: known difference, allowed diff

### Governance

**Ruling**:
A keeper decision that binds the Foundry, recorded with his words in `RULINGS.md`.
_Avoid_: ADR, decision (for an unrecorded one)

**Promotion**:
Moving a mechanism out of one work or profile into the engine, after it has a second use.
_Avoid_: extraction, upstreaming, generalising

**Tenant**:
The side of a work that stays with it when its mechanisms are promoted: its rituals, apparatus and data.
_Avoid_: using it for the content files themselves (those are the work's sources and assets) *(proposed)*
