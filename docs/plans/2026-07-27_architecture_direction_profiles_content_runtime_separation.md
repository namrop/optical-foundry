---
uid: 019fa45f-01b2-7186-bf7f-c1a0997ae92e
kind: note
note_role: architecture_note
validation_profile: standard
status: active
created: 2026-07-27T12:45:00-04:00
updated: 2026-08-03T03:15:26-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry — Architecture Direction: profiles, content, and runtime separation"
tags:
  - optical-foundry
  - architecture
  - profiles
  - asset-roots
  - non-regression
  - direction
  - luis-ruled
summary: "Luis-ruled architecture direction (2026-07-27) ahead of a dedicated design session: profiles decouple from runtime so the engine can be released publicly with profiles as configuration; content (images/assets) decouples from profiles because it is data, not engine; and nothing in the existing profile set may regress. Establishes that 'book' is the largest format the Foundry supports, not the frame to design around. Finds that the first and third principles are already stated in DESIGN.md and have drifted, while asset location was never modeled at all — the root cause of 194MB of Codex 0 plates living inside the profile tree. Also records the standing goal of filtering cross-domain work up out of the codex0 profile (which is the reference implementation, not the outlier — the other profiles are legacy), with the client classification model named as the strongest generalization candidate, and the far-roadmap web-app target as a constraint on the renderer seam. Direction and evidence only; the design belongs to the session."
principal: luis
---

# Architecture Direction — profiles, content, and runtime separation

**Status: direction, not design.** Ruled by Luis 2026-07-27 ahead of a dedicated
architecture session. This document fixes the constraints and supplies the evidence so
that session starts from the position rather than rediscovering the defect list. It
deliberately does **not** propose a target architecture.

Companion: `2026-07-25_of_book_rendering_issue_register_bounded_fix_session.md` (23 issues,
ordered by leverage — the right ordering for a fix session, the wrong one for this).

Proposed implementation design: `2026-08-03_manifest_resource_roots_and_work_owned_asset_extraction.md`.

---

## 1. The three principles

**P1 — Profiles decouple from the runtime.** The engine should be releasable publicly
without shipping Luis's profiles. **Profiles become a configuration detail rather than
something baked in.** A repo split is the eventual expression of this; the split is
*future work, explicitly not now.*

**P2 — Content decouples from profiles.** Images and assets are **content — data, not
engine.** They belong with the work they illustrate, not inside the rendering engine.
Codex 0's divider plates and vignettes living in the Foundry repo is an anti-pattern.

**P3 — Nothing in the existing profile set regresses.** Codex 0 delivery can take a
smaller reach if needed; capability cannot shrink. Non-regression is the hard constraint
on any refactor.

**Framing correction that governs all three: "book" is the largest of the formats the
Foundry supports, not the frame to design around.** `codex0` is one profile inside the
`document_spine` family, sitting beside `client_report`, `mythic-letter-johannah`, `cam`,
`yugen_*`, `resume`, `elian-*`, and the `physical_sheet_profile` grids
(`labels-avery-5164`, `labels-avery-15264`, `sticker-sheet`). Designing around the book
would itself be the regression.

---

## 2. Two of the three are already stated — this is drift, not new direction

`DESIGN.md` §0 already commits to P1 and P3. The design intent is not the problem.

| Principle | Already in DESIGN.md |
|---|---|
| P1 | *"deliberately **profile-first**… The core pipeline does not hardcode which profiles exist; profiles declare themselves."* Plus the non-negotiable constraint: *"Expansion must not require core code changes — New profile = new YAML declaration + optional template/style, no pipeline edits."* |
| P3 | Non-negotiable constraint: *"Same inputs, equivalent-or-better outputs — Backward compatibility with all existing profile source material."* Reinforced in `STATE.json` (2026-05-03): the pipeline *"Supports all current profiles (mythic, yugen, resume, etc.), CAM stack bundle generation, Avery 5164 labels, sticker-sheet workflow, expansion contract for new profiles."* |

DESIGN.md §0.5 also already treats the book as a peer, not a center: its manifest-subtype
row lists *"label run, sticker sheet, composite bundle, CAM Stack, Codex 0 bundle, Forge
packet review"* as siblings. The framing correction in §1 is a **restatement of the
existing design**, not a change to it.

**P2 is the genuinely new one — because assets were never modeled at all.**

---

## 3. The unmodeled layer: assets have no home in the abstraction

DESIGN.md §0.5's layer table models source documents, manifests, bundles, packets,
projection plans, renderers, and artifacts. **It does not model assets.** Images have no
layer, no ownership rule, and no resolution contract.

With nowhere to belong, they went where the resolver could see them.

**Root cause — `engine/profile_resolver.py:157`:**

```python
asset_roots = [p for p in [local_assets] if p.exists()]
```

Asset roots are derived **solely from the profile's own local assets directory.** There is
no concept of a *content root* supplied per render. So book images had to be moved *into*
the profile tree to be addressable at all.

**Consequences that matter for planning:**

- This is not sloppiness to be tidied. **Moving the files back breaks every render** until
  the resolver learns content roots. It is a refactor, not a file move.
- **P2 is a precondition for P1.** A profile carrying one book's reveal plates cannot be
  cleanly separated *or* published — publishing the engine would ship Johannah's plates
  with it. Content-out-of-profiles is what makes profiles-as-configuration achievable.
- Two register issues are symptoms of this one cause. **Issue 12** (ornament/rail asset
  paths hardcoded in the Lua filter) and **issue 3's fix direction** — *"extend
  graphicspath roots to cover book-tree assets: `generated_media/`,
  `photos/`"* — both patch the symptom. Issue 3's direction in
  particular teaches the engine *more* book-specific paths, which drives the anti-pattern
  one level deeper. The inversion P2 implies: **the engine takes content roots as input
  and knows nothing about which book.**

---

## 4. Drift inventory (evidence, measured 2026-07-27)

**Codex 0 content inside the engine repo** — `profiles/40_latex_import/assets/codex0/v5/`,
**28 tracked files, 194 MB**:

| Directory | Files | What it is |
|---|---|---|
| `full_page_plates/` | 17 | the per-part reveal plates |
| `witness_inline/` | 10 | object vignette `_alpha` twins |
| `divider_cutout/` | 1 | the shared beam-cut leaf art |

Worth noting *where* it landed: nested inside `profiles/40_latex_import/`, the **legacy
import-compat layer**. Book content is sitting inside the engine's backward-compatibility
tree.

**Also in the working tree:** `generated/` holds **7.6 GB** of Codex 0 proofs. Gitignored,
so not repo weight — but the same category (content in the engine tree), and worth an
explicit disposition rather than silence.

**Not drift, and not to be "fixed":** `profiles/labels/` and `profiles/stickers/` are
empty stub directories; the real physical-sheet implementation lives under
`profiles/40_latex_import/` (`label_sheet.tex`, `labels_base.yaml`,
`labels_avery_5164.yaml`, `sticker_sheet.yaml`, `schemas/sticker_sheet_manifest_v1.yaml`,
plus fixtures and tests). Deleting the stubs is safe; assuming the family is unimplemented
because the stubs are empty is not.

---

## 5. The `client_report` constraint is permanent, not a gap

`client_report`'s template, defaults, and `.sty` are **gitignored client brand assets —
third-party property, not Luis's to commit.** They can never enter this repo.

This is a *design constraint*, not a backlog item:

- The non-regression check for `client_report` must be **permanently external** — a
  fixture living where the assets live, not a stopgap until someone commits them.
- It is also the profile **served over the remote MCP** (`render_report`), so it is
  simultaneously the highest-consequence and least-testable regression surface: a refactor
  can break a client deliverable path in a way this repo's own test suite cannot detect.
- Any P1 repo split must keep this working across the split boundary — it is the existing
  proof case that profiles can live somewhere the runtime does not.

---

## 6. Proposed re-sort of the 23 issues (for the design session)

The register is ordered by leverage, which is correct for a bounded fix session and wrong
for an architecture one — sorted that way it reads as a book punch-list. **Proposed** (not
ruled) three-bucket sort by *scope of applicability*:

**A. Engine-general** — would apply to any profile; the book merely surfaced them.
`2` (silent structural drops), `3` (image lowering / `of-image`), `4` (raw-LaTeX escape
hatches), `7` (fixed-page overflow), `9` (verification / exit 0 ≠ complete), `12` (asset
paths — see §3), `14` (output ergonomics), `15` (glyph fallback), `17` (widow/orphan),
`19` (paragraph model). Also `1` in its general form: a first-class *multi-source document
manifest*, which the CAM stack needs as much as the book.

**B. Physical-object** — applies to bound/printed artifacts, not documents generally.
`6` (divider/epigraph schema), `8` (spine↔disk consistency), `11` (plate appendix
lowering), `13` (imposition), `16` (duplex page model), `18` (margin geometry / trim),
`21` (creep), `22` (volumes). Note this bucket **overlaps the physical-sheet family** —
labels and stickers are physical artifacts too, and `show_cut_lines` is the same concern
as trim.

**C. Codex-0 / edition-mechanism** — the `cx0:` variant system specifically.
`5` (marker linting), `10` (edition wiring), `20` (pataphor block length), `23` (guards are
intra-file only).

The sort is the argument: **A is the engine, B is a format family, C is one profile's
mechanism.** If the architecture is right, C should be expressible as profile
configuration rather than engine behavior.

---

## 7. Generalization direction — codex0 is the reference implementation, not the outlier

**Luis, 2026-07-27:** much of what was learned building the codex0 profile is *"wider
spanning than just codex zero or even just the book objects."* The codex0 profile is the
closest thing to how he wants to operate across the whole Foundry. **The rest of the
profiles are legacy and deliberately untouched.** The standing goal: *"filter as much truly
cross-domain work up as far as possible."*

This inverts the usual hoisting instinct. Normally you generalize from the common
denominator; here the **newest, most specific profile is the mature one**, and the shared
layer is the stale one. Promotion flows *up from* codex0, not down from the base.

It also sharpens P3. **Non-regression is not the same as non-change.** The legacy profiles
must keep *working*; they are not the pattern to preserve. The thing being protected is
their output, not their design.

**Symptom in miniature — capability that is already engine-level but wears a profile's
name.** `engine/codex_editions.py` is general machinery (audience-conditional content with
fail-closed guards) sitting in `engine/`, but named for one profile and keyed to that
profile's `cx0:` marker vocabulary. The capability generalized; the naming never did.

**The strongest concrete candidate — and it serves paid client work.** `client_report`
renders *"internal, client-confidential, and public"* documents, but its `classification`
field is **marking only**: cover and running-header treatment, defaulting to
`highly-confidential` when omitted, hard-erroring on unknown values. The fail-closed
instinct is already there — but only at the label layer. There is **no content gating**:
producing internal / client / public versions of one assessment means maintaining separate
source documents that drift.

That is precisely what `codex_editions.py` already does — one source, N audience branches,
guarded regions that fail closed when an edition has no override. The Codex 0 edition model
and the security-classification model are **the same abstraction at different stakes**.
Generalizing it would let one assessment source render three audience versions with the
gating enforced rather than remembered.

(Register issue 23 — guards are intra-file only, with no node-level scope — is therefore
not a Codex 0 issue. It is a limitation of a general capability, discovered through the
book.)

Other candidates worth triaging the same way, from `engine/`: `layout_images.py`,
`emoji_substitution.py`, `font_resolver.py`, `dropcap_assets.py`, `page_size.py` read as
general; `imposition.py`, `bindery_preflight.py`, `delivery.py` read as physical-object
(bucket B in §6), which is a family, not a profile.

---

## 8. Roadmap horizon — non-PDF targets

**Luis, 2026-07-27 (explicitly far out on the roadmap):** compiling *"a tree or a document
into a web app of some kind."*

Recorded now because it constrains the architecture even while deferred:

- It **tensions with a stated non-negotiable.** DESIGN.md §0: *"Pandoc remains the sole
  render engine."* Pandoc emits HTML, but a web app is more than an HTML target. Whether
  that constraint holds, narrows to "Pandoc remains *a* renderer," or is scoped to print
  targets is a design-session question — not something to settle by drift.
- **The seam already exists in the design.** §0.5 models a *projection plan / assembly
  view* as "internal compiled render IR," with the renderer as a "mechanical backend
  adapter." If that IR is genuinely renderer-agnostic, a web target is **another adapter,
  not a rewrite**. If the IR has quietly absorbed LaTeX/PDF assumptions, it is not, and the
  cost of finding out later is high.
- **A "tree" target implies content roots too** (§3): a compiled web artifact needs its
  assets resolvable and relocatable, not baked into a profile directory.
- It reinforces the framing from §1 from the other direction: if the Foundry can target a
  web app, then "book" is emphatically not the frame — it is one output among print
  formats, physical sheets, and eventually interactive ones.

---

## 9. Sequencing and non-goals

- **The repo split is future work.** Luis: not now. P2 (content out of the engine) is the
  refactor that unblocks it and can proceed independently.
- **Codex 0 delivery may take a smaller reach.** Scope on the book is negotiable;
  capability across the profile set is not (P3).
- **Do not design around the book.** See §1.
- **This document does not propose a target architecture.** That is the design session's
  work.

---

## 10. Open questions for the design session

1. What is the **asset/content layer** in DESIGN.md §0.5's abstraction — and what supplies
   content roots to a render? Manifest, profile, invocation, or a resolution chain?
2. Do **content roots** compose with profile-local assets (a profile still owns its own
   ornaments and fonts), or is the split absolute?
3. What is the **boundary object** for a P1 split — a profile package format? A registry?
   How does a profile declare its asset dependencies without carrying them?
4. Does the `physical_sheet_profile` family generalize to cover the **Codex 0 label
   contract** (cover label + three spine labels, non-uniform sizes, one running/rotated
   title), or does that want per-cell geometry in `sticker_sheet_manifest_v1`? The current
   schema is a uniform grid — single `grid: [rows, cols]`, one `cell_size`.
5. How does the **MCP surface** move with the architecture? It currently exposes
   `list_profiles`, `render_report`, `render_manifest`, `contact_sheet`, and HTTP mode
   collapses to `render_report` alone — the pre-book, report-era model, with no counterpart
   to issue 1's proposed book/manifest input.
6. What is the **non-regression harness**, given §5 says part of it can never live here?
7. Which capabilities **filter up out of codex0** (§7), and what is the promotion test — the
   `codex_editions.py` → client-classification generalization is the first candidate, and
   it has a paying use case.
8. Is the **projection plan / assembly view IR renderer-agnostic today**, or has it absorbed
   LaTeX/PDF assumptions? This decides whether the far-roadmap web target (§8) is an adapter
   or a rewrite, and it is cheap to answer now and expensive to answer later.
