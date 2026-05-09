---
uid: 019e0b47-4df3-7df3-8e67-1ad40b6fdad9
kind: note
note_role: architecture-design
validation_profile: standard
status: active
created: 2026-05-09T01:45:00-04:00
updated: 2026-05-09T01:45:00-04:00
beam_home: 42_optical_foundry_greenfield
title: "Illuminated Letter Profile Path"
summary: "Future path for Optical Foundry mythic-letter evolution after comparing a typeset letter with a hand-made one: stationery-plus is explicitly wanted, illuminated mode is the current new-profile goal, and page-composition mode is deferred until after Codex 0 except for ad-hoc manual experiments."
tags:
  - optical-foundry
  - mythic-letter
  - johannah
  - illuminated-profile
  - stationery-plus
  - codex-0
---

# Illuminated Letter Profile Path

## Context

After comparing the final rendered **typeset letter** artifact with the true handwritten/illustrated **hand-made letter** artifact, the useful renderer gap became clearer.

The goal is **not** to die on the hill of handwriting. Handwriting is one possible intimacy signal, but the more important transferable features are:

- semantic artwork integrated with the page;
- motif-driven ornaments and illustrations;
- color emphasis that means something;
- page-rhythm review through screenshots/contact sheets;
- ceremonial thresholds, pull quotes, and closing seals;
- a repeatable profile path that can make dense personal letters feel carried by beauty rather than merely typeset.

## Path decision

### 1. Stationery-plus mode — explicitly wanted

Stationery-plus mode should be treated as a desired Foundry capability.

It extends the existing Johannah mythic-letter profile without becoming a full page-composition engine.

Likely features:

- stable Johannah stationery header/footer;
- multiple named raster-art slots beyond a single `header_art`;
- optional transparent PNG overlays;
- motif-aware header, margin, watermark, and closing-seal assets;
- semantic color roles for selected lines;
- automatic PDF rasterization and contact-sheet generation for artifact review;
- no-overwrite preview output directories.

This is the practical bridge between current typeset-letter rendering and more embodied mythic artifacts.

### 2. Illuminated mode — current goal for the new profile

The current goal for the new profile is an **illuminated letter** mode.

This should remain Pandoc/LaTeX-backed, but allow source annotations and YAML/frontmatter fields to carry intentional artifact semantics.

Likely capabilities:

- semantic source annotations such as vow, confession, blessing, thesis, pull quote, or closing blessing;
- profile-level color palette roles for those annotations;
- named art slots such as opening threshold art, motif illustration, margin emblem, pull-quote panel, closing tailpiece, watermark sigil, and footer glyph;
- generated or selected raster artwork integrated as part of the artifact language;
- support for readable typed body text while allowing selected script/handmade-style elements when useful;
- evidence outputs that include page screenshots/contact sheets, not only the final PDF.

This should be the near-term profile-design target.

## Out of scope for now

### Page composition mode — deferred until after Codex 0

Full page-composition mode is out of scope until after **Codex 0** is done.

That mode would treat each page as an explicit designed field rather than relying primarily on linear document flow. It may eventually support page plans such as:

```yaml
pages:
  - role: threshold
    art: opening_threshold
    emphasis: salutation
  - role: density
    art: margin_emblem
    emphasis: pull_quote
  - role: closing
    art: closing_seal
    emphasis: blessing
```

But implementing that as a general Foundry subsystem would be a larger architecture step. Until Codex 0 is complete, page-composition experiments may happen **ad hoc** for individual artifacts, but they should not become the main profile mandate.

## Practical implementation order

1. Keep the existing Johannah mythic-letter profile stable.
2. Add stationery-plus support first: additional art slots, semantic color roles, contact-sheet evidence.
3. Use a typeset letter and a hand-made letter as reference artifacts for validating the feel.
4. Build illuminated mode as the new profile target with explicit source annotations and motif-art slots.
5. Defer generalized page-composition planning until after Codex 0, except for manual one-off experiments.

## Design compression

Do not make Foundry chase handwriting. Make Foundry able to carry mythic meaning through **stationery, semantic color, motif artwork, illuminated emphasis, and closing ritual** while preserving readability and repeatable render mechanics.
