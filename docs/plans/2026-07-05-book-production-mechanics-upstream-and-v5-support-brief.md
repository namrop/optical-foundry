---
uid: 019f33f6-c1f0-7da4-be98-a773406955b3
kind: note
note_role: handoff
validation_profile: standard
status: draft
created: 2026-07-05T19:30:00-04:00
updated: 2026-07-06T20:30:00-04:00
beam_home: 42_optical_foundry
title: "Session Brief — Book-Production Mechanics Upstream + v5 Support"
summary: "Starting brief for a Foundry work session that generalizes hand-bound book production beyond Codex 0 and adds the mechanics v5 needs: a spine→codex_bundle bridge, signature-aware plate placement, a per-sheet stock/furnish map so dividers and plates can be printed on cardstock, divider page-tagging, edition selection wired into render, breath/split rendering, and reliable book-level paragraph indentation (the recurring parindent / \\\\-litany raggedness fixed upstream instead of per-block). Grounds each ask in existing Foundry surfaces (render.delivery.imposition, section_dividers[], of-image plates, PROFILE_AND_PANDOC_REFERENCE parindent standard, evidence sidecars) so this extends rather than reinvents. Item 9 (added 2026-07-06) fixes the bridge default that currently emits a full-page divider at every chapter: chapters should open with an inline heading + optional small epigraph, with dividers reserved for part boundaries. Item 10 (added 2026-07-06) fixes the compiler's unconditional per-source \\newpage so passages within a chapter breathe (item-6 breath surface) instead of each starting a new page, which is inflating the page count; page breaks become boundary-aware (part/chapter only)."
tags:
  - optical-foundry
  - render-manifest
  - bound-pdf
  - imposition
  - signature-aware-plates
  - codex0-v5
  - book-production
  - indentation
  - parindent
recipient_ready: false
print_ready: false
proposal_ready: false
---

# Session Brief — Book-Production Mechanics Upstream + v5 Support

## Why this session exists

Codex 0 has reached a point where the manuscript (now a full-tree v5 baseline, ~74.6k words / 108 passages / 11 parts) needs a real Foundry render path, not a throwaway pandoc concat. The v4 page-count probe went *around* the Foundry — the spine manifest is explicitly "a structure/spine manifest, not an Optical Foundry document manifest," and no v4/v5 `codex_bundle` render manifest exists. That gap is the trigger.

But the goal is bigger than Codex 0. **Codex 0 will not be the only book.** The mechanics we build here should be book-agnostic Foundry capabilities driven by manifest, not codex0-specific special cases. Three concrete production needs are driving the design:

1. **Signature-aware plate rendering** — plates (full-page images, photographed physical artifacts) need to land on *known physical leaves* of a folded signature, not wherever the text flow happens to push them.
2. **Divider page-tagging + stock map** — the render must tell us *which output pages* the dividers (and plates) land on, so those specific sheets can be printed on cardstock / different stock, with the right image on the right side.
3. **Print-on-cardstock workflow** — closing the loop from "manifest says this is a divider/plate" to "load cardstock in the tray for sheet N side B and print this image there."

## What already exists (build on, don't reinvent)

Read these before designing anything:

- **`contracts/IMPOSITION.md`** — `render.delivery.imposition` (manifest-owned) and the `impose` CLI already produce `booklet_signature_2up` layouts with an `.imposition.json` sidecar that records per-signature, per-sheet **front/back page-slot maps** and marks padded blanks as `null`. This slot map is the spine of the "which physical leaf" problem — signature awareness already exists at imposition time; today it just isn't fed *back* into placement decisions.
- **`contracts/BUNDLE_ASSEMBLY.md`** + `section_dividers[]` — divider pages already support recto/right-page forcing, blank-after insertion, source-backed vs. manifest-authored dividers, divider-local profile hooks, background images, and divider-faithful numbering (`render.numbering_strategy: section_dividers`). Divider *placement* is solved; divider *stock-tagging* is the new part.
- **`docs/bound-delivery-status-2026-05-18.md`** — mirrored margins, outer page numbers, colophon, running headers, illumination rails, imposition, bindery preflight sidecars. The bound-delivery instrumentation to extend.
- **`docs/guides/figure-wraps.md`** + `of-image` / `of-initial` source blocks, and manifest `figures:` — the plate-rendering primitives. Full-page plates likely want a manifest-owned placement contract rather than overloading `figures:` (the README already flags this).
- **`docs/guides/codex0-edition-variants.md`** — how cx0 johannah/witness/reader editions are expressed. v5 render selection must consume this.
- **Evidence JSON sidecars** — already carry page count, warnings, boundary assertions. The natural carrier for the new stock/furnish map.
- **`kind: codex_bundle`** manifest family (`bundle_manifest_v1`) — the target manifest type for a book.

## Work items

### 1. Spine → codex_bundle bridge (unblocks everything)
The codex0 v5 spine manifest (`21_letters_and_creative/book/codex0_v5/manifests/codex0-v5-spine-working-2026-07-05.yaml`, schema `codex0_spine_manifest_v0`) is the order authority but is not Foundry-renderable. Build the bridge: either a generator that projects a spine manifest into a `codex_bundle` render manifest, or teach the Foundry to consume the spine schema directly. Decide which. This is the first deliverable — it turns the 108-passage tree into a real render and replaces the pandoc estimate with a profile-accurate page count.
- Must respect the spine's `render_policy`: manifest-owned numbering, part-level `00_divider.md` between parts, chapter dividers as-needed (not every one), `codex_edition_default: johannah`.
- Keep it book-agnostic: the bridge consumes *a* spine, not codex0's specifically.

### 2. Signature-aware plate placement (the core new capability)
Today placement is text-flow-driven and imposition is a post-pass. Add a placement mode where a plate declares a **signature-relative target** and the compiler pads/positions so the plate lands there. Design questions to resolve:
- Target vocabulary: e.g. `plate.leaf: {signature: next|N, position: front|back|own_leaf}` — enough to say "this plate on its own leaf, on the front side of a fresh signature."
- Interaction with `signature_size`: placing on a known leaf implies padding to align; the compiler must reconcile plate targets with signature boundaries and report the padding it inserted.
- Round-trip: placement decisions and the resulting imposition slot map must agree. The `.imposition.json` front/back slot map is the verification surface.
- Bleed: plates printed to the edge need full-bleed geometry distinct from the text block's mirrored margins.

### 3. Stock / furnish map (the print-shop handoff)
Emit a **per-sheet furnish map** in the evidence sidecar: for each physical sheet (post-imposition), which stock it's on (text stock vs. cardstock vs. specialty), which output pages it carries, and what prints on each side. This is what lets Luis (or a shop) load cardstock for the right sheets and print the right image. Requirements:
- Driven by page-role tagging: dividers and plates carry a `stock:` (e.g. `cardstock`) and optional `print_image:` in the manifest; the compiler propagates the tag from output page → imposed sheet-side → furnish map.
- Handle the case where a cardstock divider/plate and a text page share a sheet-side after imposition (flag it — you can't mixed-stock a single sheet; may force padding so cardstock pages get their own sheets).
- Human-readable furnish summary alongside the JSON (a print run-sheet), since this is operated by hand.

### 4. Divider page-tagging
Extend `section_dividers[]` so a divider can declare stock + an image-to-print-on-the-stock, feeding items 2/3. Part dividers are the first consumer (Codex 0 has 11). Keep the tag general: any book's dividers, not codex0's.

### 5. Edition selection wired into render
The bridge/render must accept a `codex_edition` selection (johannah|witness|reader) and resolve cx0 variant/guard blocks accordingly, guards failing closed. Default `johannah` per spine policy. This is a prerequisite for producing the actual recipient edition, not just a page-count proof.

**Ground-truth (2026-07-05 walk):** the mechanism is *already implemented* — see `docs/guides/codex0-edition-variants.md`. cx0:variant/edition markers are preprocessed before Pandoc; `codex_edition` and `codex_strip_editorial_callouts` are honored from either source frontmatter or manifest `variables:`; guards fail closed; evidence carries `codex_edition_*` keys. The remaining work is small: the bridge must propagate `codex_edition_default: johannah` from the spine `render_policy` into the bundle manifest `variables:` and honor a per-render `codex_edition` override. Not a mechanism build; a wiring pass.

### 6. Breath / split rendering
v5 ratified a "split on function, breathe on render" policy (`codex0_v5/structure/codex0_v5_splitting_and_breaths_policy_2026-07-05.md`): a renderer breath at every passage boundary plus an inline `<!-- cx0:breath -->` marker. The Foundry needs to honor both — passage-boundary spacing and the inline breath marker — as generic typographic surfaces.

### 7. Reliable paragraph indentation (make the recurring "indentation is funny" problem go away)
Indentation is a recurring complaint and it needs to become a book-level guarantee, not a per-block hand-fix. The mechanism is already documented — `docs/PROFILE_AND_PANDOC_REFERENCE.md` §"Paragraph indentation control (parindent)". Read it first; it is the standard. The relevant failure modes for a litany-heavy literary book:

- **The `\\`-litany raggedness (the main one).** LaTeX indents only the *first line* of a paragraph by `\parindent`. A markdown block whose lines are broken with two trailing spaces (`\\`) is **one paragraph**, so a refrain/litany renders as "first line indented, rest flush." Codex 0's profile currently sets `parindent: "1.2em"` (`profiles/40_latex_import/defaults/codex0.yaml`) and the book is full of `\\`-broken refrains — so this raggedness is live across the manuscript. The current remedy is a per-block `` `\noindent{}`{=latex} `` prefix, which does **not** scale across 108 passages.
- **The ragged2e / `\justifying` clobber (latent).** `codex0.tex` loads `ragged2e` (line 27) but does not currently call `\justifying`, so the clobber is not active *today* — but it's a landmine: if any future edit or shared-template change introduces `\justifying` after the `parindent` setlength, the `parindent` variable silently stops working. Harden against it so `\parindent` stays authoritative regardless of ordering (re-issue after any `\justifying`).

**Upstream goal: a deliberate, book-level paragraph model that renders reliably without per-block tagging.** Two paths, and this is a design call for Luis:
- **(a) Flush paragraphs** (`parindent: 0pt` + vertical `parskip`) — the robust default for verse/litany-heavy text; the `\\`-litany problem disappears entirely because there is no first-line indent to strand. Trades the classic book look for reliability.
- **(b) Keep classic first-line indent** and make the compiler handle litanies structurally — detect blocks that use `\\` line breaks (or an authored verse/litany marker) and render them in a flush/verse environment (e.g. `obeylines`-style, every line flush) so the indent only ever applies to true prose paragraphs. This preserves the indented-prose look and fixes the raggedness generically instead of per-block.

**Ground-truth (2026-07-05 walk):** the semantic-class infrastructure path (b) needs already partly exists. `filters/codex0_composition.lua` + `profiles/40_latex_import/templates/codex0.tex` already lower Codex composition classes into `CodexBreath` / `CodexVow` / `CodexThreshold` / `CodexHeldObject` / `CodexWitness` / `CodexAxiom` / `CodexQuoteBlock` / `CodexTailpiece` minipage environments. Any `\\`-litany already routed through a Codex class can be made flush by setting `\parindent=0pt` inside those minipages — a small template change, no per-block tagging, no book-wide reversal. This makes a **hybrid path** available:
- keep `parindent: 1.2em` document-wide for classic prose;
- reset `\parindent` to `0pt` inside the `Codex*` environments so class-routed litany blocks render flush by construction;
- add a `codexverse` (or `codexlitany`) env in the composition filter for any remaining `\\`-broken content that is *not* class-routed.

Whichever path, the deliverable is: a book renders with correct, consistent indentation from the manifest/profile alone, no `\noindent{}` sprinkling. Keep it book-agnostic — a profile-level paragraph-model contract, not a codex0 patch. Template-level changes flip every document on the profile, so treat them as deliberate, confirmed changes.

**Ratified (2026-07-05): path (a) flush + parskip.** The `\\`-litany pattern the brief describes is not present in v5 (zero `  $` line-break litanies; zero codex composition class markers). The live pattern is *paragraph-break litany* — one line, blank line, next line — which under classic first-line indent renders as a stacked indented list rather than a litany. The 2026-07-05 probe (`fixtures/manifests/codex0_v5_parindent_probe_2026-07-05.codex-bundle.yaml`) rendered the vow chapter + "The Circle That Would Not Stay Closed" under both postures on the codex0 profile; flush read as a vow, baseline read as a cluttered indented list. Landed:
- `profiles/40_latex_import/defaults/codex0.yaml`: `parindent: "0pt"` + `parskip: "0.6em"` (was `1.2em` + `3pt`).
- `profiles/40_latex_import/templates/codex0.tex`: `\OFReissueParindent` at `\AtBeginDocument` — kills the ragged2e/`\justifying` landmine even if a future edit introduces `\justifying`.

The hybrid path (parindent=0 inside Codex composition envs) remains available if v5 later routes litanies through composition classes, but is not needed today.

### 8. Back-matter apparatus (endnotes wiring first)

Whole-book renders now have real front matter (title page + colophon on the title verso + TOC), but back matter is still just whatever the assembled body ends up emitting after the last passage. The v5 tree has an authored back-matter directory at `21_letters_and_creative/book/codex0_v5/backmatter/`:

- `00_backmatter_scaffold.md`
- `01_notes_endnotes_placeholder.md`
- `02_glossary_placeholder.md`
- `03_index_placeholder.md`
- `04_appendices_witnesses_placeholder.md`
- `05_how_this_book_was_made_full.md`
- `06_source_uid_register_placeholder.md`
- `99_final_threshold_question_physical_sidecar.md`

Item 8 is the surface that lets the bridge wire these into the render. Two coupled sub-items:

**8a. Endnotes wiring (highest priority, self-contained spec landed).** See `docs/plans/handoff_codex0_endnotes_wiring_2026-07-06.md`. Authors reference notes as inline pandoc footnotes (`[^id]` … `[^id]: …`) in passage markdown; today the codex0 profile renders them as bottom-of-page footnotes. Luis wants them to collect into a single back-matter Notes section, auto-numbered in reading order, with **no manifest edit and no per-note bookkeeping**. Atrium side is already in place — `backmatter/01_notes_endnotes_placeholder.md` carries a guarded `\ifdefined\theendnotes\begingroup\renewcommand{\notesname}{}\theendnotes\endgroup\fi` print sink that stays inert until the OF preamble defines `\theendnotes`. OF-side patch is minimal: in `profiles/40_latex_import/templates/codex0.tex` (or as `header-includes` in `codex0.yaml`),

```latex
\usepackage{endnotes}
\let\footnote\endnote
```

Notes: manifest-level `header-includes` cannot ride through — the `_guard_manifest_variables` allowlist intentionally rejects list-valued / LaTeX-control-token variables — so the preamble must live in the profile/template. Codex0 renders under lualatex (verify `endnotes` works there — it does). Composition filter (`filters/codex0_composition.lua`) interaction should be verified via a Part IX ch.2 probe (that passage has 6 real `[^18b-*]` footnotes, the fastest live check). The remap is global, so any `\footnote` in future frontmatter also becomes an endnote. `\theendnotes` placement stays Atrium-owned (inside `01_notes_endnotes_placeholder.md`) — do NOT put `\theendnotes` in the template.

**8b. Backmatter-source wiring in the bridge.** The current spine→bundle bridge only reads `spine[].chapters[].passages[]`; it has no notion of backmatter. To include the backmatter files above (including the endnotes sink), the bridge needs one of:
- a `--backmatter-dir <path>` CLI flag that reads all `.md` files from a dir in sorted filename order and appends them as `sources[]` with `role: appendix`;
- or a `--backmatter <path>` flag (repeatable) for explicit file selection;
- eventually, a first-class `backmatter:` array in `codex0_spine_manifest_v0` so backmatter is spine-authoritative like the body.

MVP is the CLI flag; spine-schema promotion is a follow-up. Backmatter sources render after the body and before the auto-emitted provenance block. Numbering strategy stays `section_dividers` — backmatter files have their own `# Notes` / `# Glossary` etc. H1 headings.

**Acceptance (8a):** probe-render Part IX ch.2 (or the full book) via the codex0 bundle manifest with `--backmatter-dir` including at least `01_notes_endnotes_placeholder.md`, and confirm:
1. the six `[^18b-*]` footnotes no longer print at the bottom of their pages,
2. they appear as a numbered list in the back-matter Notes section under the single `# Notes` heading, in reading order,
3. hyperref links (if active) work forward from body to notes and back.

### 9. Chapter dividers off by default + inline chapter openings (fixes "a divider at every chapter")

**Defect (found 2026-07-06).** The spine→bundle bridge (`21_letters_and_creative/book/codex0_v5/tooling/spine_to_bundle_manifest.py`) defaults `--chapter-dividers` to **`always`** (argparse, ~line 494). With that default it emits a `-chapter-divider` section_divider for *every* chapter, each `force_right_page: True` (emission at ~lines 325–347, labeled "the epigraph surface"). The 2026-07-06 whole-book bundle (`manifests/generated/codex0-v5-whole-book-2026-07-06.codex-bundle.yaml`) therefore carries **67 section_dividers** — ~11 part dividers plus one full-page divider per chapter. This contradicts item 1's own requirement ("chapter dividers as-needed (not every one)") and the spine `render_policy` (`chapter_dividers: ... do not render every chapter divider by default`). Symptom Luis sees: a divider page opening every chapter, and chapter epigraphs each eating a whole recto.

**Desired model (Luis, 2026-07-06).** Dividers belong at *part* boundaries only. A chapter opens with a chapter heading plus an *optional, small* epigraph that sits at the top of the chapter's first page and shares that page with the body — it does **not** take a whole page. Chapters may still begin on a fresh page (normal book behavior), but that is a chapter *opener*, not a divider.

**Two coupled changes:**
1. **Default away from `always`.** Change the bridge default to `when-file-exists` (emit a chapter surface only when a chapter `00_divider.md` is deliberately authored) or `off`. This alone makes section_dividers part-boundary-only. One-line, reversible.
2. **Render the chapter opening inline, not as a divider page.** Even when a chapter carries an epigraph, it must render as a chapter opener (title + small epigraph, in-flow), not a `force_right_page` section_divider that consumes a recto.

**Coupling tradeoff to resolve (do not skip).** The codex0 bundle sets `numbering_strategy: section_dividers`, which forces `suppress_source_wrapper_headings=True` (`engine/manifest_compiler.py` ~line 997) — so **chapter titles currently ride on the chapter-divider pages**. If the default merely flips to `off`/`when-file-exists`, chapters that lose their divider also lose their visible title. So the correct fix is *convert* the chapter opening from divider-page → inline chapter heading + optional epigraph, not just *delete* chapter dividers. Options:
- emit the chapter opener as a per-chapter source-wrapper heading (un-suppressed for the chapter's first passage) with any epigraph as an in-flow block beneath it; or
- add a dedicated inline chapter-opener surface (title + optional epigraph block, no `force_right_page`, no `\clearpage`) that the bridge attaches to the chapter's first passage.

Also note the bundle compiler emits an unconditional `\newpage` before every source (`engine/manifest_compiler.py` ~line 1080); that is what makes each chapter start on a fresh page even independent of dividers. Decide whether chapter openers keep that fresh-page start (classic) or flow within the part.

**Acceptance.** Regenerate the whole-book bundle and confirm: (a) section_dividers count drops to part dividers only (~11, plus any plate leaves), with **zero** per-chapter `force_right_page` dividers; (b) each chapter opens with a visible title and, where authored, a small epigraph sharing the page with the chapter body; (c) part dividers and plate placement unchanged; (d) a probe render reads as "part divider = full page, chapter = opener-in-flow." Keep it book-agnostic: a bridge default + chapter-opener rendering model, not a codex0 special case.

### 10. Passages within a chapter must breathe, not page-break (every passage currently starts a new page)

**Defect (found 2026-07-06).** The bundle compiler emits an **unconditional `\newpage` before every source** in the main assembly loop (`engine/manifest_compiler.py` ~line 1080, inside `for src in sorted_sources:`). Because v5 splits each chapter into one source *per passage* (spine policy "split on function"), every passage boundary — even *within a single chapter* — forces a fresh page. Symptom Luis sees: a passage ends a third of the way down a page, the next passage jumps to a new recto/verso, and the page count balloons. On a 108-passage book this is a large, mechanical inflation of the page count.

**Desired model (Luis, 2026-07-06).** Passages within the same chapter should be separated by **at most a breath mark** — the renderer breath from item 6's "split on function, breathe on render" policy (`codex0_v5/structure/codex0_v5_splitting_and_breaths_policy_2026-07-05.md`), i.e. centered ornament or vertical space in-flow, *not* a page break. A hard page break (`\newpage`/`\clearpage`) belongs only at **chapter and part boundaries** (and plate leaves), never between two passages of the same chapter.

**Fix direction.** The `\newpage` must become boundary-aware instead of per-source:
- Suppress the `\newpage` between two sources that belong to the **same chapter** (the bridge already knows chapter membership — sources carry chapter grouping via the spine projection; expose it to the compiler, e.g. a per-source `page_break_before: false` / `boundary: passage|chapter|part` hint the bridge sets, defaulting passage-internal boundaries to no break).
- At a same-chapter passage boundary, emit the item-6 breath surface (renderer breath + honor any inline `<!-- cx0:breath -->`) instead of the page break, so passages are separated by an ornament/space envelope.
- Keep the page break at the *first* source of a chapter (chapter opener, per item 9) and at part boundaries.

This is coupled to items 6 and 9: item 6 supplies the breath surface that replaces the break; item 9 owns the chapter-opener page-break decision. Resolve them together so the boundary model is coherent — *part boundary → full-page divider; chapter boundary → chapter opener (fresh page, per item 9); passage boundary → breath, no page break.*

**Acceptance.** Regenerate the whole-book bundle and confirm: (a) two consecutive passages in the same chapter render on the same page when they fit, separated by a breath ornament/space, with **no** intervening `\newpage`; (b) chapters and parts still begin on fresh pages; (c) total page count drops materially versus the per-passage-page baseline (the 450pp v4 render was passage-broken); (d) inline `<!-- cx0:breath -->` markers still render where authored. Keep it book-agnostic: a boundary-aware page-break contract, not a codex0 patch.

## v5-specific consumers to keep in view

- **Part X (`10_witnesses_and_plates`)** is the plate chain: literal images of two-way artifacts in chronological order, minimal exposition (dateline + one-line caption), order authority `21_letters_and_creative/book/codex0/timelines/codex0_letters_and_two_way_artifacts_timeline_2026-07-01.md`. It is the primary stress test for items 2–4. Some artifacts also render as inline plates in their home chapters (a card, a set of synthesis pages) — same-artifact repetition to reconcile at wiring.
- **Part dividers on cardstock** with printed images = the direct motivating case for items 3–4.
- Adjudication authority for what v5 renders: `codex0_v5/INDEX.md` §Control surfaces (part layouts, repetition/register policy, sensitive-passage pass, review adjudications).

## Suggested starting sequence

1. Item 1 (spine→codex_bundle bridge) — get a real Foundry render of v5 and a profile-accurate page count; this validates the pipeline end-to-end. Item 7 (indentation) is a natural companion here: the first full render is where the `\\`-litany raggedness will show up everywhere, so settle the paragraph model at the same time. **(Landed 2026-07-05; item 5 wiring, item 7 paragraph model, and three front-matter fixes shipped.)**
2. Item 8 (back-matter apparatus) — endnotes wiring + bridge backmatter-source hook. Small, self-contained, unlocks reader-facing whole-book renders that include Notes / How This Book Was Made / etc. **(Landed 2026-07-06.)**
3. Item 4 + 3 (divider tagging → stock/furnish map) on the 11 part dividers — smallest real cardstock case. **(Landed 2026-07-06: `section_dividers[].stock` + `print_image` propagate to evidence, bridge exposes `--part-divider-stock` / `--chapter-divider-stock`, `engine/furnish.py` computes per-sheet-side stock via `[[OFDIV:<uid>]]` marker extraction against `.imposition.json`, and the renderer writes `.furnish.json` + `.furnish.txt` next to the imposed PDF. First v5 cardstock render lands 11 part dividers on 22 sheet-sides of 244 total; each cardstock sheet-side is flagged mixed because saddle-stitch imposition pairs each cardstock leaf with a text-stock leaf — expected, and now visible to the print shop / hand-binder.)**
4. Item 2 (plate placement) — **redefined 2026-07-06 by Luis: Part X removed from the spine; plates disperse to 2 per part, printed onto the same cardstock sheet as the part divider (divider leaf + plate leaf, 4 cardstock pages per part boundary), arranged in the signature and sewn. Not tipped in.** The bridge now takes `--plates-dir <path>` and reads `plate_NN_<part_slug>_<a|b>.md` files, injecting each pair as source-backed section_dividers with `stock: cardstock` immediately after the corresponding part divider, so the physical order is: divider recto → blank verso → plate A recto → plate B verso. **Landed 2026-07-06 as a staging spot** with 20 placeholder plates at `21_letters_and_creative/book/codex0_v5/plates_staging/`; when real plate images arrive Luis swaps the file bodies without touching the pipeline. No signature-aware-placement machinery was needed under this model — the cardstock envelope is just 4 consecutive pages at each part boundary, and imposition treats them as ordinary consecutive pages.
5. Item 6 (inline cx0 ornament markers) — **redefined and landed 2026-07-06.** The brief scoped this to just the `<!-- cx0:breath -->` marker; Luis pointed out that breath is one of many ornamentation types in the Codex composition grammar (landing, breath, hinge, tailpiece, rail-echo, threshold, vow, vow-block, axiom, quote, witness, source-note, held-object as blocks; signal, heartword, smallcaps, quiet, bold as inline emphasis; per-primitive asset pools + local overrides). `.codex-*` div classes and span emphases already work via `filters/codex0_composition.lua` → `codex0.tex` environments. The gap was the inline marker family — HTML comment triggers with no wrapped content, useful for intra-passage pacing. `codex0_composition.lua` now grows a `RawBlock` handler that lowers six inline marker families:

- `<!-- cx0:breath -->` / `cx0:tailpiece` / `cx0:hinge` / `cx0:threshold` — centered break-in-flow ornament, each pulling the next asset from its pool via `\CodexBreakOrnament`;
- `<!-- cx0:rail -->` — outer-margin companion, via `\CodexRailCompanion` (recto/verso-aware under bound delivery, `\marginpar` fallback otherwise), pulling from the rail pool (RE01, RE03, RE04, RE06, RE08, RE09, B04, B08);
- `<!-- cx0:landing -->` — pure vertical spacing, no ornament per the grammar.

Each marker also accepts an optional `asset="ID"` attribute to pin a specific asset from the pool (matching the `.codex-*` div grammar's override syntax), and `asset="none"` to suppress the ornament while keeping the pause/spacing envelope:

```markdown
<!-- cx0:breath -->                  <!-- pool default, cycles -->
<!-- cx0:breath asset="B09" -->      <!-- pinned to B09 -->
<!-- cx0:breath asset="none" -->     <!-- suppressed, spacing only -->
<!-- cx0:rail asset="RE04" -->       <!-- pinned rail companion -->
```

The vocabulary is extensible — one entry per new marker type in `inline_ornament_by_marker`. Verified end-to-end on v5 Swan Song passage (6 authored `<!-- cx0:breath -->` markers now render as B06/B09/T10/FH04/B01/B02 breath ornaments in reading order).

6. Item 9 (chapter dividers off by default + inline chapter openings) — **open, added 2026-07-06.** The bridge default (`--chapter-dividers always`) currently emits a full-page divider at every chapter, contradicting item 1 and the spine policy. Flip the default and convert the chapter opening to an inline heading + optional small epigraph, keeping chapter titles that currently ride on the divider pages. Smallest first step: change the default and probe-render to confirm section_divider count collapses to part boundaries; then wire the inline chapter-opener rendering.
7. Item 10 (passages breathe, not page-break) — **open, added 2026-07-06.** The compiler's unconditional per-source `\newpage` (`engine/manifest_compiler.py` ~line 1080) forces every passage onto a new page, inflating the page count. Make the page break boundary-aware (part/chapter only); replace same-chapter passage boundaries with the item-6 breath surface. Resolve jointly with items 6 and 9 so the part/chapter/passage boundary model is coherent.

## Open design questions

- Chapter-opener rendering (item 9): un-suppress per-chapter source-wrapper headings, or add a dedicated inline chapter-opener surface? And do chapter openers keep the per-source fresh-page start, or flow within the part?
- Boundary-aware page breaks (item 10): where should the passage/chapter/part boundary hint live — a per-source `boundary:`/`page_break_before:` field the bridge sets, or does the compiler re-derive chapter membership from source grouping? And is the same-chapter passage separator a fixed breath, or the authored `<!-- cx0:breath -->` when present and a default breath otherwise?

- Bridge as generator vs. native spine consumption? (Affects whether the spine schema becomes a first-class Foundry input.)
- Where does the plate placement contract live — extend `figures:`, or a new `plates:` / anchor-placement contract? (README leans toward a dedicated contract.)
- Can the compiler reason about signature geometry *before* the final imposition pass, or does placement need a two-pass (render → measure → re-pad → impose) loop?
- Mixed-stock-on-one-sheet: hard error, or auto-pad cardstock pages onto their own sheets (wasting the verso)?
- Paragraph model (item 7): flush (`parindent: 0pt`) or classic first-line indent with structural litany handling? A book-wide decision that sets the profile default.

## Notes

- `42_optical_foundry` is a git submodule (`gitdir: ../.git/modules/42_optical_foundry`); commits here are submodule commits, separate from the canon repo. No active validation hook in the submodule, but match the docs' Atrium frontmatter convention.
- The v4 pandoc probe (throwaway, uncommitted, `/tmp`) landed ~322 flowing / ~370 passage-broken pages at half-letter 11pt; realistic finished ~400pp with front matter, dividers, plates, and the real `codex0_handbound` illumination margins. **The first Foundry v4 render (2026-07-05) landed at 450 pages: title page, colophon on title verso, TOC, 108 body passages with 21 johannah-edition variants selected, 48 LER callouts stripped, zero warnings.**
- v4 is tagged `codex0-v4-complete-2026-07-05` for a pinned source snapshot if a v4 render is ever wanted.
- **2026-07-06: v5 is complete and is now the primary render target.** V4 remains as a pinned baseline. Future renders should point the bridge at `21_letters_and_creative/book/codex0_v5/manifests/codex0-v5-spine-working-*.yaml`.
