---
uid: 01a11d76-1139-7228-8d8d-ffc35ab0f7f7
kind: note
note_role: architecture_note
validation_profile: standard
status: active
created: 2026-10-08T17:40:39-04:00
updated: 2026-10-08T17:40:39-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry render backend — one-year language check: hold Pandoc/LaTeX, revisit triggers recorded"
summary: "One-year maintenance/rearchitecture check (2026-10-08) of whether Optical Foundry should drop Pandoc or unify rendering on HTML/JS/TS. Verdict: hold the Pandoc/LaTeX press; a TS rewrite would not collapse the language split because the book lane stays on TeX either way; explicit revisit triggers recorded, default next check October 2027."
tags:
  - optical-foundry
  - architecture
  - render-pipeline
  - pandoc
  - latex
  - typescript
  - annual-check
  - decision-record
author:
  name: Lux
  harness: hermes-agent
  model: claude-opus-5-5
  provider: anthropic
last_touched:
  name: Lux
  harness: hermes-agent
  model: claude-opus-5-5
  provider: anthropic
  at: 2026-10-08T17:40:39-04:00
principal: luis
---

# Optical Foundry render backend — one-year language check

## Pith

At Optical Foundry's one-year mark the keeper asked whether the Pandoc/LaTeX render path should be dropped for an HTML/JS approach; the check keeps the Pandoc/LaTeX press and records explicit revisit triggers for the next evaluation.

## Abstract

On 2026-10-08 the keeper re-opened the render-backend question as a maintenance and re-architecture check, motivated by the language split across the estate and by good HTML-derived PDFs seen elsewhere. The check separated Pandoc (a stateless Markdown-to-TeX lowering step, not where the complexity lives) from TeX (where the real weight lives), found that a JS/TS rewrite would not collapse the render-path split because the book lane stays on TeX either way, and confirmed that the estate's seams are language-agnostic files, contracts, and services. The keeper approved recording the verdict: hold the current spine, with explicit revisit triggers, default next check October 2027.

## 1. Question and frame

The keeper's framing (T3 Code session over Hermes ACP on Sol, 2026-10-08; session id not captured in-band): the driver is the language split across the estate, plus checking that no better way is being left unexamined. His words: "It is a maintenance/rearchitecture question. Not leaving assumptions unturned. I can drop it for the next year or so. It is about a year since I started building OF, so worth checking again."

Two candidate changes were examined:

1. Drop Pandoc and render from HTML (motivated by good HTML-derived PDFs seen elsewhere).
2. Simpler still, drop LaTeX as well and render from JS/TS.

## 2. What the check found

1. **Pandoc is not the complexity.** It is a stateless lowering step (Markdown + profile defaults to TeX) invoked as one subprocess by `renderers/pandoc_renderer.py`. Dropping it specifically would mean hand-writing the Markdown parsing it provides for free. The felt complexity is TeX: the rerun loop, error archaeology, macro surgery (drop-cap exclusion geometry, columnsep tucks), alpha-PNG re-encoding, and font fallback work.
2. **A JS/TS rewrite would not collapse the split.** The book lane (Codex 0) stays on TeX under any near-term candidate, so "unify on JS" swaps a Python wrapper around TeX for a TS wrapper around TeX; the render path remains two-worlds. The rewrite price (golden tests, regression lanes, rulings, reference corpus all pin behavior to the current implementation) would be paid for no language unification in the lane that matters most.
3. **The feature-blocker list is a "haven't built it" list, not a law of nature.** The keeper's correct counter: drop-cap text exclusion, contour wraps, and the Lua page-position law do not exist in a JS engine because none was built. In an owned engine those features are straightforward; they are only hard in browsers because CSS abandoned exclusions. The genuine price is TeX's free paragraph machinery: Knuth-Plass line breaking, hyphenation quality, justification, floats, multi-pass cross-references. Assembling equivalents (harfbuzzjs, Knuth-Plass ports, hyphenopoly, pdf-lib) into a book-grade engine is a multi-month project that would be visibly worse than TeX for a long time.
4. **The estate's seams are language-agnostic.** Optical Foundry's interfaces to everything else are PDFs, evidence JSON, manifests, and service surfaces (`service.py`, `mcp_serve.py`); the MCP direction (HTTP-transport servers, tool schemas over per-harness docs) is the estate's actual unification layer. In an agent-plus-contract estate with pinned toolchains, language homogeneity buys much less than it does for a human team. A TS backend would also not reduce runtimes — the Python engine stays for manifests and evidence.
5. **The complexity observation that survives the check:** the engine is already a layout engine wrapped around TeX (Lua page-position law, wrapfigure overrides, image bake, MediaBox normalization). Complexity has been displaced into TeX archaeology rather than avoided. That is the strongest argument for the keeper's direction and is what the revisit triggers watch.
6. **Prior rulings and constraints touched by the question.** `DESIGN.md` lists "Pandoc remains the sole render engine" as a ratified non-negotiable constraint; the renderer adapter seam allows a peer output adapter as an extension, not a replacement. The 2026-05-10 ruling held web output out of scope for the source-preparation refactor (session scope, not forever). Browser-based rendering (Chromium + Paged.js) is credible for report/screen lanes but is a larger dependency object than TeX on NixOS, not a smaller one, and pagination strains at book scale. Typst is the only candidate that would genuinely collapse book-lane complexity (single binary, no rerun loop, scriptable), but it is its own language rather than TS, still young for book-grade work, and a swap re-earns the scar-tissue class the reference corpus holds; it is a per-lane backend evaluation, not a language-unification play.

## 3. Verdict

Hold. The Pandoc/LaTeX press stays the spine for book lanes; no TS rewrite of the engine. The keeper reviewed the analysis in conversation and approved recording this position. This note is a keeper-reviewed decision record that maintains the existing ratified constraint (`DESIGN.md` non-negotiables) rather than replacing it; nothing about the architecture changed.

The concrete action the check flagged is not architectural: execute the ruled 2026-09-28 performance plan (parallel volume renders, measure mode, image pre-bake), since compile time and error archaeology were part of the original discomfort and are attacked inside the current stack for a fraction of a rewrite.

## 4. Revisit triggers

Re-open the backend question before the default date if any of these fire:

1. A real (non-spike) commitment to a web UI over Optical Foundry — decide TS-core versus TS-client-over-service at that point.
2. Typst looks book-grade, or a new book lane starts fresh — per-lane backend evaluation.
3. TeX pain resumes dominating sessions after the 2026-09-28 performance plan lands — same evaluation.
4. Default: next annual check, October 2027.

## 5. Related surfaces

- `42_optical_foundry/DESIGN.md` — ratified constraint "Pandoc remains the sole render engine"; expansion contract and renderer adapter seam.
- `42_optical_foundry/docs/plans/2026-09-28_codex0_build_performance_plan.md` — measured build cost and the ruled performance plan (the in-stack attack on render pain).
- `42_optical_foundry/docs/plans/2026-08-25_press_component_and_publication_readiness.md` — the Pandoc/LaTeX fixed-page pipeline named as the press component.
- `42_optical_foundry/docs/plans/2026-07-27_architecture_direction_profiles_content_runtime_separation.md` — profiles decouple from runtime; relevant to any future backend adapter work.
- `42_optical_foundry/RULINGS.md` — ruling ledger; the 2026-05-10 source-preparation ruling scoped web output out of that refactor.
