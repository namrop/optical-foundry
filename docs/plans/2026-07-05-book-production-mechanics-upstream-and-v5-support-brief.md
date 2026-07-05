---
uid: 019f33f6-c1f0-7da4-be98-a773406955b3
kind: note
note_role: handoff
validation_profile: standard
status: draft
created: 2026-07-05T19:30:00-04:00
updated: 2026-07-05T19:30:00-04:00
beam_home: 42_optical_foundry
title: "Session Brief — Book-Production Mechanics Upstream + v5 Support"
summary: "Starting brief for a Foundry work session that generalizes hand-bound book production beyond Codex 0 and adds the mechanics v5 needs: a spine→codex_bundle bridge, signature-aware plate placement, a per-sheet stock/furnish map so dividers and plates can be printed on cardstock, divider page-tagging, edition selection wired into render, breath/split rendering, and reliable book-level paragraph indentation (the recurring parindent / \\\\-litany raggedness fixed upstream instead of per-block). Grounds each ask in existing Foundry surfaces (render.delivery.imposition, section_dividers[], of-image plates, PROFILE_AND_PANDOC_REFERENCE parindent standard, evidence sidecars) so this extends rather than reinvents."
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

## v5-specific consumers to keep in view

- **Part X (`10_witnesses_and_plates`)** is the plate chain: literal images of two-way artifacts in chronological order, minimal exposition (dateline + one-line caption), order authority `21_letters_and_creative/book/codex0/timelines/codex0_letters_and_two_way_artifacts_timeline_2026-07-01.md`. It is the primary stress test for items 2–4. Some artifacts also render as inline plates in their home chapters (a card, a set of synthesis pages) — same-artifact repetition to reconcile at wiring.
- **Part dividers on cardstock** with printed images = the direct motivating case for items 3–4.
- Adjudication authority for what v5 renders: `codex0_v5/INDEX.md` §Control surfaces (part layouts, repetition/register policy, sensitive-passage pass, review adjudications).

## Suggested starting sequence

1. Item 1 (spine→codex_bundle bridge) — get a real Foundry render of v5 and a profile-accurate page count; this validates the pipeline end-to-end. Item 7 (indentation) is a natural companion here: the first full render is where the `\\`-litany raggedness will show up everywhere, so settle the paragraph model at the same time.
2. Item 4 + 3 (divider tagging → stock/furnish map) on the 11 part dividers — smallest real cardstock case.
3. Item 2 (signature-aware plate placement) with Part X as the proving ground.
4. Items 5–6 fold in as the render matures toward an actual recipient edition.

## Open design questions

- Bridge as generator vs. native spine consumption? (Affects whether the spine schema becomes a first-class Foundry input.)
- Where does the plate placement contract live — extend `figures:`, or a new `plates:` / anchor-placement contract? (README leans toward a dedicated contract.)
- Can the compiler reason about signature geometry *before* the final imposition pass, or does placement need a two-pass (render → measure → re-pad → impose) loop?
- Mixed-stock-on-one-sheet: hard error, or auto-pad cardstock pages onto their own sheets (wasting the verso)?
- Paragraph model (item 7): flush (`parindent: 0pt`) or classic first-line indent with structural litany handling? A book-wide decision that sets the profile default.

## Notes

- `42_optical_foundry` is a git submodule (`gitdir: ../.git/modules/42_optical_foundry`); commits here are submodule commits, separate from the canon repo. No active validation hook in the submodule, but match the docs' Atrium frontmatter convention.
- The v4 pandoc probe (throwaway, uncommitted, `/tmp`) landed ~322 flowing / ~370 passage-broken pages at half-letter 11pt; realistic finished ~400pp with front matter, dividers, plates, and the real `codex0_handbound` illumination margins. The first Foundry render should replace this number.
- v4 is tagged `codex0-v4-complete-2026-07-05` for a pinned source snapshot if a v4 render is ever wanted.
