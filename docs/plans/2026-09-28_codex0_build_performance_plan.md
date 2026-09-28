---
uid: 01a0e9c7-ccbc-7c7f-a9a5-2069c083284e
kind: note
note_role: architecture_note
validation_profile: standard
status: active
created: 2026-09-28T16:50:00-04:00
updated: 2026-09-28T19:17:00-04:00
beam_home: 42_optical_foundry
title: "Codex 0 build performance — measurements and the ruled plan"
tags:
  - optical-foundry
  - codex0
  - performance
  - pass-orchestration
  - images
  - luis-ruled
summary: "Measured cost of the three-volume Codex 0 build on 2026-09-28 (about 50 minutes, eight sequential full renders on an 8-core host) and where it goes: sequential renders, image bytes (Volume III is 433 MB, 432.7 MB of it images), alpha PNGs re-encoded on every LaTeX run, and full post-processing on renders that exist only to harvest page labels. Records the ruled plan: parallel reading-volume renders and a measure mode first, then draft-mode measurement passes and a restructured pass order as the B3 promotion, then an image pre-bake cache whose downsampling stays a keeper call."
author:
  name: Claude Opus 5.5
  harness: claude_code
  model: claude-opus-5-5
  provider: anthropic
  voyage: "claude-code:session:96cb72ec-b737-4efa-bd76-d5e173d514bf"
  at: 2026-09-28T16:50:00-04:00
last_touched:
  name: Claude Opus 5.5
  harness: claude_code
  model: claude-opus-5-5
  provider: anthropic
  voyage: "claude-code:session:96cb72ec-b737-4efa-bd76-d5e173d514bf"
  at: 2026-09-28T19:17:00-04:00
ruling_refs:
  - uid: 01a0e9c7-c01e-7d0a-bcc0-4793b00abce0
    relation: authorizing-ruling
related:
  - path: docs/plans/2026-08-25_codex0_capability_promotion_map.md
    kind: note
    relation: implements-b3
principal: luis
---

# Codex 0 build performance — measurements and the ruled plan

## Pith

The Codex 0 build takes about fifty minutes because it renders eight full volumes one at a time and re-encodes every alpha image on every LaTeX run; the ruled plan cuts that in three steps.

## Abstract

The three-volume build (`codex0_v5/build/run_full_build.sh`) was measured on 2026-09-28 during the regression baseline for the G1/A3/F1/E1 refactor. It performs eight full renders in sequence on an eight-core host, most of which exist only to learn where page numbers land. The volumes carry 200 to 430 MB of images, and because LuaTeX cannot pass an alpha PNG through, every soft-masked image is decoded and recompressed on every LaTeX run of every render. Each render also runs the full post-processing chain, including a second typeset of the whole PDF for the safe-area overlay. The keeper ruled the recommended order: parallel reading-volume renders and a measure mode first, then draft-mode measurement passes and a single final render wave as the B3 promotion, then an image pre-bake cache, whose downsampling is a separate keeper call because it changes pixels.

## 1. Measurements (2026-09-28, Foundry `aa3bd9e`, run `of-refactor-baseline-aa3bd9e-2026-09-28`)

The build runs one render at a time.

| Pass | Renders | Needs the PDF for |
|---|---|---|
| A2 | Vol I | last page label only |
| B2 | Vol II | last page label only |
| C2 | Vol I, Vol II (sequential) | the reading volumes with full Contents |
| D1a | Vol III | its own page labels only |
| D1b | Vol III | final Vol III |
| G2 | Vol I, Vol II (sequential) | final reading volumes |

Eight full renders, about 50 minutes wall clock.

Per-render cost, from evidence `render_duration_ms` and file times on the C2/D1b renders:

| Volume | Pages | PDF | Compile | Post-processing after compile |
|---|---|---|---|---|
| I | 224 | 208 MB | 129 s | about 60 s |
| II | 286 | 426 MB | 149 s | about 70 s |
| III | 126 | 434 MB | 322 s | about 30 s |

Image load (`pdfimages -list`, object byte counts):

- Vol I: 522 image objects, 255 soft masks; 27 full-page plates at 2200×3400.
- Vol II: 668 image objects, 324 soft masks; 57 full-page plates at 2200×3400.
- Vol III: 168 image streams carry **432.7 MB of the 433 MB file**; the largest are about 2600×4000 at 20–22 MB each, set small in the apparatus.

Why the images cost time and not only bytes: LuaTeX embeds an opaque PNG by copying its data, but an alpha PNG must be decoded, split into colour and soft mask, and recompressed. That happens on every LaTeX run pandoc makes while cross-references settle, in every one of the eight renders. Volume III's 322 s compile on 126 pages is that cost.

Post-processing on every render: divider-marker sanitizing (a PDF rewrite), `pdftotext` twice, glyph lint, bindery preflight (`pdfimages`/`pdffonts` over the whole file), and the safe-area overlay, which typesets a second copy of the entire PDF. Passes A2, B2 and D1a need none of it.

## 2. The plan (ruled 2026-09-28)

Ruling `01a0e9c7-c01e-7d0a-bcc0-4793b00abce0` (`RULINGS.md`): "agreed. lets do your recommendation". The recommendation, in order:

**Step 1 — no output change, after the refactor lands.** *Done 2026-09-28 (§4).*

1. Render Volume I and Volume II in parallel in C2 and G2. They are independent. About 6 minutes saved.
2. A measure mode for `cli manifest` that skips the safe-area overlay and bindery preflight on intermediate renders. About a minute saved on each of five renders.

**Step 2 — the B3 promotion (pass orchestration).** *Done 2026-09-28 (§5).*

3. Draft mode for the passes that only need page labels. Graphicx `draft` keeps every image's box dimensions, so pagination is unchanged and no image data is processed. The existing gates (C3, D1c, G3) become the proof: the final render's labels must equal the draft's, or the build stops.
4. Restructure the passes: draft Volume I, draft Volume II seated, draft Volume III, emit every final bundle with every locator known, then render all three final volumes at once. One full-render wave instead of eight. Estimate: about 50 minutes to about 10–12. The roman-frontmatter invariant the script already relies on (a Contents row cannot move an arabic body folio) is what makes this sound, and it stays asserted rather than assumed. This is candidate B3 on the promotion map. *As built (§5), the engine carries B3's assertion half — draft renders and the draft-versus-final gate — and the pass order stays in the book's build script: by the promotion map's own test a pass planner with one consumer is a contract, not yet code. It moves when the corpus book needs multiple passes.*

**Step 3 — images.**

5. Pre-bake images once into a content-addressed cache: convert alpha PNGs to a form LuaTeX embeds by copy, and downsample each image to what its placed size needs at print resolution. Every compile gets cheaper, and files shrink roughly five to ten times, which speeds up everything downstream. **Downsampling changes pixels and remains the keeper's call**; a lossless variant (convert only, no downsampling) is available if he wants zero visual change.

Also noted, not yet ordered: skip re-rendering a volume whose inputs are unchanged (evidence already records source digests).

## 3. Verification

Every step is checked the way the 2026-09-28 refactor was: the regression lane (the build with STEP 0 skipped, so no build number is claimed and no colophon is restamped) renders from the candidate Foundry, and the result is compared with the previous run by contact sheet per volume (reading and bind PDFs), page counts, bundle manifests and resolved sources. Steps 1 and 2 must produce identical contact sheets. Step 3 is judged by the keeper against the sheets and a print sample.

## 4. Step 1 — done, 2026-09-28

Foundry `cli manifest --measure` (commit "build performance step 1") and the book's
`run_full_build.sh`: passes A2, B2, C2 and D1a render in measure mode; C2 and G2 render Volumes I
and II in parallel. D1b (Volume III) and G2 (Volumes I and II) are the only full renders, so the
shipped artifacts still carry their bindery preflight and safe-area overlay.

| Run | Foundry | Wall clock |
|---|---|---|
| `of-refactor-candidate-f424794-2026-09-28` (before step 1) | `f424794` | about 49 min (17:03–17:52) |
| `of-perf-step1-9184675-2026-09-28` | step-1 branch | **42.4 min** (2,545 s) |

About 7–8 minutes saved, 15%, as estimated. Verification: every gate passed with the same
shapes (224 / 288 / 128), and contact sheets for all three volumes, reading and bind, plus bundle
manifests and resolved sources, are identical to the pre-step-1 run.

What remains is the render count itself: eight full LaTeX compiles, each re-encoding every alpha
image. That is step 2 (B3) and step 3.

## 5. Step 2 — done, 2026-09-28

Engine (Foundry commit "build performance step 2"): `cli manifest --draft` (implies `--measure`;
pandoc `--include-in-header` with `\setkeys{Gin}{draft=true}`; evidence `render_mode: draft`) and
`cli renders-agree <reference> <candidate>` (`engine/pass_gates.py`: page count, the label of every
page, the outline by level, title, page and destination height; exit 66 naming the first
difference).

Proved before wiring, each volume's draft against its full render from the step-1 run: identical
page count, every page label, every page's text (the draft's own image-box labels aside) and the
outline.

| Volume | Full compile | Draft compile |
|---|---|---|
| I | 129 s | 26.7 s |
| II | 149 s | 27.1 s |
| III | 322 s | 14.3 s |

Book (`run_full_build.sh`): every render before the final wave is a draft into
`vol{1,2,3}_draft/`; PASS W renders the three final bundles full and in parallel into
`vol{1,2,3}/`; the new PASS H proves each final against the draft of the same bundle with
`renders-agree`; D1d (the Volume III parity law) moved onto the final; C3, D1c and G3 still gate
the drafts; PASS F reads only the finals' resolved sources. Every `say` line carries a timestamp and
the build prints its total.

Measured, run `of-perf-step2-cab52d1-2026-09-28`, **827 s (13.8 min)**:

| Pass | Seconds | | Pass | Seconds |
|---|---|---|---|---|
| A1 emit | <1 | | D1b emit + draft III | 17 |
| A2 draft I | 63 | | G1 emit | 3 |
| B1 emit | <1 | | G2 draft I + II (parallel) | 36 |
| B2 draft II | 64 | | **W final I, II, III (parallel)** | **413** |
| C1 emit | 3 | | H renders-agree ×3 | 2 |
| C2 draft I + II (parallel) | 34 | | D1d parity | <1 |
| D1 emit | 3 | | **D2 plate containment** | **167** |
| D1a draft III | 15 | | E bind shapes | 4 |

Verification: every gate passed with the same shapes (224 / 288 / 128), PASS H reported the same
shape for all three volumes, and contact sheets for all three volumes, reading and bind, plus bundle
manifests and resolved sources, are identical to the step-1 run.

**Where the time is now.** The final wave (Volume III's full render sets it, slower in parallel than
alone) and plate containment are 70% of the build. The wave is step 3's target — every image
re-encoded on every LaTeX run. Plate containment (`tooling/check_plate_containment.py`, three
volumes in sequence) is new on the floor list; it reads the finals, so it can at least run its three
volumes in parallel, or during the wave's tail. Not ordered yet.
