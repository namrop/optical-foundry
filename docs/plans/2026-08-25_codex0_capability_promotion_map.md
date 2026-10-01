---
uid: 01a039a9-23fb-7c3d-aa95-b3f9ee3cb6c4
kind: note
note_role: architecture_note
validation_profile: standard
status: draft
created: 2026-08-25T12:05:00-04:00
updated: 2026-10-01T16:40:00-04:00
beam_home: 42_optical_foundry
title: "Codex 0 → Optical Foundry — capability promotion map (post-delivery)"
tags:
  - optical-foundry
  - codex0
  - promotion
  - architecture
  - decision-survey
  - ratification-partial
  - proof-render
summary: "Post-delivery survey answering open question 7 of the 2026-07-27 architecture direction: which capabilities filter up out of codex0, and what the promotion test is. Adds a second driver the direction doc did not have — arbitrary-Atrium-corpus books (keeper captures, convergence logs) as a review instrument, not only a print target. 25 candidates in seven bands, each with its current home, its generalization, a non-codex0 use case, and blast radius. Also records the custody audit of the delivered copy: everything that made the book is committed, and almost none of it is pushed. Ratification partial: G1, A3, F1 and E1 were ruled PROMOTE on 2026-09-28 and done the same day (§8); the rest are unruled. §7 (2026-09-01) records the first keeper-capture proof render: compiled, final PDF withheld by the glyph lint, two engine gaps found."
principal: luis
ruling_refs:
  - uid: 01a0e9ab-077c-7836-b986-8cb968ad2155
    relation: authorizing-ruling
  - uid: 01a0e9c7-c01e-7d0a-bcc0-4793b00abce0
    relation: b3-promotion
  - uid: 01a0ea08-7757-7f0f-9176-4316debc18d6
    relation: part01-plate-intended
  - uid: 01a0f458-a0ce-7a10-a6b9-927a52a976cb
    relation: step-1-defects-and-f2
last_touched:
  name: Claude Opus 5.5
  harness: hermes-agent
  model: claude-opus-5-5
  provider: custom:primary
  voyage: "t3-code:hermes-acp"
  at: 2026-10-01T16:40:00-04:00
---

# Codex 0 → Optical Foundry — capability promotion map

## Pith

Which Codex 0 capabilities move up into Optical Foundry, by what test, in what order, and which have moved.

## Abstract

This survey answers the 2026-07-27 direction note's question 7: which capabilities filter up out of the Codex 0 book into the engine, and what test a capability has to pass to move. It adds a second driver beside print, the corpus book used as a review instrument, and lists 25 candidates in seven bands with their current home, generalization, second consumer and blast radius. It also records the custody audit of the delivered copy and the first keeper-capture proof render. The keeper ruled the sequencing for its first two steps on 2026-09-28: the Foundry and canon were tagged at the Codex 0-compatible state, and G1, A3, F1 and E1 were promoted the same day; every other candidate is still unruled.

**Status: survey, partly ratified.** G1, A3, F1, E1 ruled PROMOTE and done 2026-09-28 (§8,
ruling `01a0e9ab-077c-7836-b986-8cb968ad2155` in `RULINGS.md`). Everything else is unruled.

Companion / parent: `2026-07-27_architecture_direction_profiles_content_runtime_separation.md`.
This document answers that one's **open question 7** — *"Which capabilities filter up out of
codex0, and what is the promotion test?"* — and supplies a second driver it did not have.

---

## 1. Precondition — custody of the delivered copy

Audited 2026-08-25, ten days after build 100. **The finding is: committed, not pushed.**

### 1.1 What is sound

- **Build 100** (`volumes-hundredth-impression-final-part05-lux-light-2026-08-15`,
  `build_ledger.yaml`) stamped canon head **`5ca886a59`** with **no `-dirty` suffix**. The
  freeze-stamp gate did its job: the hash identifies the text that rendered.
- `5ca886a59` is an ancestor of canon `master`. Working tree carries no Codex 0
  modifications.
- The submodule pin at `5ca886a59` and at `master` agree: Foundry **`54b8d29`**. The Foundry
  working tree is clean.
- **Input closure verified.** The three build-100 bundle manifests reference **204** absolute
  canon paths. All 204 resolve on disk. **169 are tracked in git.** The **35 untracked are all
  under `codex0_v5/generated/volume_apparatus/`** — part-divider leaves, half-plate versos,
  ask pages, harvested contents and notes — every one of them emitted by
  `spine_to_bundle_manifest.py` during the build. Nothing authored is missing.

So the delivered copy is **reproducible from committed state**, on this disk.

### 1.2 What is not sound

| # | Gap | Detail |
|---|---|---|
| C1 | **Canon `master` is 617 commits ahead of `origin/master`** | Deneb tip is `648391b2c`, 2026-08-14 03:00. **Build 100's commit is not on any remote.** The `github` mirror is staler still — 2026-07-16. |
| C2 | **~314 Git LFS objects are unpushed** | Including `codex0_v5/.../codex0_v5_part05_building_the_lighthouse_ethereal_full_page_plate_5p5x8p5_400dpi.png` — the Part V reveal, the ritual payoff. The binary exists in one place. |
| C3 | **Foundry `54b8d29` is unreachable from every remote ref** | 126 commits ahead of `origin/main` (tip `7278b78`, 2026-07-16). A clone of canon cannot check out the renderer that made the book. The submodule pointer is dangling for anyone but this host. |
| C4 | **The Foundry work was never merged to local `main` either** | 48 commits on `dev/codex0-contained-rail-ladder-20260802`. Two side branches hold 1 commit each not in HEAD: `failed/codex0-rail-compositor-20260801`, `feature/contour-wrap-alpha-spike`. |
| C5 | **The delivered artifacts themselves are gitignored** | `.gitignore:219,220` exclude `codex0_v5/generated/` and `codex0_v5/manifests/generated/`. The three build-100 volume PDFs, their `_bind.pdf` twins, the exact bundle manifests, and their SHA-256s are not preserved in git. Reproducible in principle; not archived in fact. |
| C6 | **Backup posture unverified** | No canon backup timer was visible from this session. Not asserted either way — needs a look. *2026-09-01 23:51 EDT, keeper: the build-100 PDFs are "the first target for backup to Sagittarius A* when that is up" — the deep-archive/LTO host in the placement future-shape spec (`20_digital_architecture/specs/pharos_host_service_placement_future_shape_v0_2026-06-04.md`), not yet built.* |

**Ruling wanted (custody):**

- [x] **C-A** — Push canon `master` + LFS to `origin`, and mirror to `github`. *Done 2026-09-01 (lane 1): origin, deneb and github all current, LFS 0 pending.*
- [x] **C-B** — Merge the Foundry dev branch to `main` and push. *Ruled 2026-09-01 23:32 EDT — keeper: "we can merge into main for now, and then do the refactoring work." Done the same night: `main` fast-forwarded to the dev tip (zero commits were on `main` that the dev branch lacked) and pushed to deneb and origin.*
- [x] **C-C** — Preserve the delivered artifacts deliberately. *Done 2026-09-02 00:07 EDT.* Manifests + SHA-256s were committed under `docs/delivery/build-100/` (lane 1, `8438ab7`). PDF home ruled 2026-09-01 23:44 EDT — keeper: "if it's codex 0 it should probably live in LFS. Something else I haven't agreed on yet." — then 23:51: "let's do deneb only for now. I don't want to pay for that 2.1 GB. It is the first target for backup to Sagittarius A* when that is up." The six build-100 volume PDFs (reading + `_bind` per volume, ~2.1 GB) are in **canon** LFS at commit `950c4f70a`, force-added because canon's `.gitignore:220` excludes the parent directory and git cannot re-include a child of an excluded directory; all six oids match `SHA256SUMS`. *Deneb-only did not survive contact:* GitHub rejects any push carrying LFS pointers whose objects it lacks (GH008), so the mirror blocked every lane's push until the keeper chose (00:04 EDT) to push the objects to github as well — the mirror already held ~17 GB of canon LFS, so a data pack almost certainly exists and 2.1 GB more is likely within it. Both remotes now hold the objects. Non-Codex-0 render artifacts remain unruled. **Backup:** these six are the first named target for the Sagittarius A* deep-archive host when it is up (see C6).
- [x] **C-D** — Adjudicate the two orphan Foundry branches. *Ruled 2026-09-01 23:44 EDT: "the foundry branches that are orphaned we should tag." Done: annotated tags `archive/failed-codex0-rail-compositor-20260801` and `archive/feature-contour-wrap-alpha-spike`, pushed to deneb and origin. Branch refs left in place; deleting them is a separate small step.*

~~None of the promotion work below should start before **C-A/C-B**.~~ C-A and C-B are closed
as of 2026-09-01; the copy is no longer the only one. Promotion work may start once the
candidates below are ruled.

---

## 2. The frame

The three ratified principles stand unchanged: **P1** profiles decouple from runtime, **P2**
content decouples from profiles, **P3** nothing in the existing profile set regresses. And the
framing correction stands: *book is the largest format the Foundry supports, not the frame to
design around.*

**What is new since 2026-07-27 — a second driver, and it is not a print driver.**

Codex 0 was a print target. The next use is a **review instrument**: compose a long-form bound
PDF out of arbitrary Atrium files — every keeper capture, or every convergence log — and read
it as one object. Two payoffs, and the second is the load-bearing one:

1. It can be printed. That was always the plan.
2. **It can be read for drift.** Fifty files seen as one paginated body, with running heads,
   a linked contents, and register marks in the margin, surfaces repetition, contradiction,
   and rot that fifty separate reads never will. And it can be redlined by hand.

This changes the promotion test. The direction doc's test was implicitly *"would another
profile want this?"* The sharper test is:

> **The promotion test.** A capability promotes when it can be stated without naming Codex 0,
> the book, or Johannah — *and* a second, already-wanted consumer exists. If it can be stated
> generically but has no second consumer, it is a **contract**, not yet code: write the
> contract, leave the implementation in the profile.

Consumers available to argue against, today: the **keeper-capture book**, the
**convergence-log book**, `client_report` (paid, and permanently external per §5 of the
direction doc), `mythic_letter_johannah` (already grew a half-letter bound-object lane on this
branch), and the far-roadmap web target.

**A warning that belongs at the top.** Most of what follows is *not* in this repo. It is
**7,462 lines of Python and shell inside one book's working directory** —
`codex0_v5/tooling/` and `codex0_v5/build/`. `spine_to_bundle_manifest.py` alone is **4,548
lines**, against **10,240 lines for the entire Foundry engine**. The book compiler is not a
subordinate of the Foundry; it is currently larger than the Foundry's core, and it lives
where nothing can find it. That is the single biggest structural fact in this survey.

---

## 3. The candidate ledger

Seven bands. **Tier** marks what the keeper-capture / convergence-log book actually needs:
**★ = required**, **○ = follow-on**. Each candidate is `[ ]` — unruled.

### Band A — Source selection and composition

The band that makes "compose a book out of arbitrary Atrium files" possible at all.

- [ ] **A1 ★ — The spine → bundle compiler.** *Now:* `codex0_v5/tooling/spine_to_bundle_manifest.py`, 4,548 lines. *Goes to:* `engine/` as a first-class compiler beside `manifest_compiler.py`. *Generalization:* an ordered tree of sources (part → chapter → passage) with manifest-owned numbering, projected into a bundle manifest. Nothing in that sentence is about a memoir. *Second consumer:* both new books. *Blast radius:* total — this is the book. Must be split from its codex0-specific generators (see §4) before it can move. **The largest single item here, and the one everything else in Band A waits on.**

- [x] **A2 ★ — Selection manifests (query-driven source sets). NEW, not a promotion.** *Built 2026-09-30 as step 2 of the ruled order (`RULINGS.md` 01a0f458-a0ce), as a selector that emits the bundle manifest (the 2026-09-01 "manifest should be authoritative" ruling) — §10.* *Now:* does not exist. Codex 0's spine is 682 lines of hand-authored YAML naming every file. *Wanted:* select sources by predicate — beam + `note_role` + tag + date range + status — and order them (chronological by `created`, by beam, by uid, by explicit override), emitting a spine A1 then compiles. *Second consumer:* this **is** the keeper-capture book; there is no other way to build it. *Note:* this is the one candidate that is genuinely new construction rather than relocation, and it is the gate on the whole new-use-case.

- [x] **A3 ★ — Frontmatter-driven epigraph harvest + layered attribution grammar.** *Now:* split — harvest in `spine_to_bundle_manifest.py::_read_divider_epigraph`, lowering in `engine/manifest_compiler.py` (`_inline_chapter_opener_epigraph_lines`), typography in `codex0.tex` (`\CodexOpenerEpigraph`, ratified 2026-07-28), with a generic `\OFChapterOpenerEpigraph` fallback already present. *Generalization:* any Atrium file may carry `epigraph_*` fields; the engine harvests them; the profile decides how they set. The layered model — dramatic line (speaker/context) over bibliographic line (author/source/translator/date), with `epigraph_register` inverting upright/italic — is already general, and its hardest-won rule (**`epigraph_date` means when the work was authored, which is why the translator slot exists**) is a corpus rule, not a book rule. *Blast radius:* low; the fallback macro already exists. **Closest to ready of anything in this survey.** *PROMOTE, ruled 2026-09-28 (`RULINGS.md` 01a0e9ab-077c); done the same day — §8.*

- [ ] **A4 ○ — Deterministic source UIDs and provenance comment.** `_source_uid`, `_provenance_comment`. Stable identity for a composed source, derived from its position; the manifest carries a comment naming spine, edition, parts, delivery mode. Generic. *Second consumer:* every composed document.

- [ ] **A5 ○ — Extent measurement.** `_measure_sources_words`, `_round_words`, `words_to_english`. Word extent of a source set, and its rendering as English prose for a colophon. Generic and small.

### Band B — Multi-volume and cross-reference machinery

- [x] **B1 ★ — Volume splitting with continuous folio seating.** *Built 2026-10-01 as step 3 (`engine/volumes.py`, manifest `volumes:`) — §11.* *Now:* `--volume {I,II,III}` + `--body-folio-start` in the book tooling, plus the **physical-sheet parity law** (`12ef7af`, print-critical: folio parity must match physical parity or `twoside` puts the outer rail in the gutter — build 45/46 shipped that defect and it looked fine on screen). *Generalization:* one logical document, N physical volumes, one continuous folio run. *Second consumer:* a keeper-capture corpus is large enough to want volumes on the first try.

- [x] **B2 ★ — Linked contents via PDF page-label harvest.** *Built 2026-10-01 as step 3, the contents of the whole work (`render.work_contents`) — §11.* *Now:* `_pdf_part_pages`, `_page_footer_folios`, `_volume_locator_rows`, `_reading_volume_locator_rows`. *The doctrine, and it is the reusable part:* **folio authority is PDF page labels, not printed footers.** Printed-folio scraping undercounts every time a volume ends on suppressed leaves — plates and trailing blanks own a folio and print none. Build 56 seated Vol II at a duplicate folio because of exactly this. Label arithmetic on both sides agrees by construction. *Second consumer:* any multi-file bound corpus wants a real contents.

- [ ] **B3 ★ — Multi-pass render orchestration with fixed-point proofs.** *Now:* `build/run_full_build.sh`, 511 lines, passes A · B · C · D1..D1d · G1..G3 · D2 · E · F. **This is the item Luis named directly** ("the multiple passes to do a linked table of contents across volumes"). *Generalization, and the thing worth promoting is the contract more than the code:* **a pass that consumes a prior render's labels must prove the prior render did not move.** C3, D1c and G3 are three instances of one gate. So is the rule attached to G3 — *if it fails, do not add a retry; past a body-folio move the fixed point is not guaranteed to exist.* The script also carries two lessons that are pure engine material: pick the **newest** bundle by mtime, not the lexically-first (a press build straddling midnight silently re-rendered a volume with no folio seat), and the CC14 **one-stamp-per-build** gate. *Blast radius:* medium — it becomes a pass planner, and the gates become engine assertions. *Note:* Luis has said this is optional-by-default. Correct — it should be a declared capability of a bundle, not a mandatory pipeline.

- [ ] **B4 ○ — Cross-volume endnote sink.** `_harvest_volume_endnotes`, `_generate_vol3_notes_source`. Inline `[^id]` across N files collecting into one apparatus volume. Directly useful for a capture corpus with citations.

### Band C — Register and edition gating

- [ ] **C1 ○ — Rename and generalize `engine/codex_editions.py`.** Already named as candidate #1 in the direction doc §7, **and it has a paying use case**: `client_report`'s `classification` field is marking-only (cover and header treatment), with no content gating — so producing internal / client / public versions of one assessment means maintaining separate sources that drift. Codex 0's edition model is the same abstraction at different stakes: one source, N audience branches, guarded regions that fail closed. *Blast radius:* medium, and it touches a client deliverable path this repo's tests cannot see (direction doc §5). *Carries with it:* register issue 23 — guards are intra-file only, no node-level scope. That is a limitation of the general capability, not a book defect.

- [ ] **C2 ○ — Marker vocabulary becomes profile-declared.** The `cx0:` prefix is hardcoded through `codex0_composition.lua` (1,388 lines) and the engine. A promoted edition mechanism needs the profile to declare its own marker namespace. Prerequisite for C1 being honest rather than renamed.

### Band D — Page furniture and typography (the ornamentation work)

- [ ] **D1 ★ — Margin register rails.** *Now:* `contracts/RAILS_CONTRACT.md` (326 lines, already written at a promotable altitude), `codex0_composition.lua`, `codex0.tex`. *Generalization:* **a rail is a run-grouped margin mark that says "the register changed here."** The contract's three rules survive de-Codexing intact — rail continuity means *story identity* (not proximity, not chapter, not page); ornaments and literal interludes are transparent both ways; every rail is a complete specimen drawn natively at its length, never a stretched stem. *Second consumer:* in a keeper-capture book, a rail per source-capture or per beam does exactly the job it does in Codex 0 — it tells the eye where one voice ends. **This is the strongest "it was never about the book" candidate in the survey.** *Carries:* run grouping (`dec2e6d`, `c7c1b39`), the per-segment stub floor (`8ac1833`), the contained-ladder rule.

- [ ] **D2 ★ — Ornament page-position law.** *Now:* `e0bc6fd`, `144de1d` — LuaLaTeX `pre_output_filter` enforcement at render time, with structural classes exempt at page top. *Generalization:* an ornament class may declare where on a page it is legal, and the law is enforced against the shipped page rather than predicted from the source. Generic to any decorated document; the enforcement-at-output-time posture is the valuable half.

- [ ] **D3 ○ — Floating plate placement and containment.** *Now:* `b7baf9b` (pre_output_filter injector, whatsit anchors, ship-flag chip folio), `c050cb3`, `cea2861`, plus the build-time gate `tooling/check_plate_containment.py` (372 lines). *Generalization:* a full-page figure seats itself under legality rules, and **containment is re-proved every render because it is not a source defect** — a correctly-seated plate is pushed onto the wrong spread by any edit upstream of it. Build 64 proved that. *Second consumer:* any illustrated long document.

- [ ] **D4 ○ — Chapter-opener contract.** `contracts/CHAPTER_OPENERS_CONTRACT.md` (160 lines), raised capitals replacing drop caps (`5e71dd2`, which fixed 32 chapters with no cap), keep-with-next (`c67bba5`), always-start-a-new-page (`cea2861`). Already a contract; needs to become profile-parameterized rather than codex0-shaped.

- [ ] **D5 ○ — Page-number-keyed head and folio suppression.** `c050cb3` — suppression keyed to the page number, not to a flag reset race. A generic `pagestyle` mechanism (`codexPlateFolioChip`, `6466133`) wearing a profile's name.

### Band E — Physical object

- [x] **E1 ★ — Signature padding to bind shape.** *Now:* `run_full_build.sh` PASS E. *Generalization:* pad a rendered PDF to a whole signature, emit a `_bind.pdf` beside the reading artifact, and hard-error on an **odd** rendered page count (a final leaf with no verso cannot be folded — do not let the pad absorb it). *Also generic:* pad leaves carry the ruled blank-leaf mark, because a bound-in blank with a mark reads as deliberate at collation and a bare blank reads as a printing error. The *choice* of mark is tenant data; the rule is not. *PROMOTE, ruled 2026-09-28 (`RULINGS.md` 01a0e9ab-077c); done the same day — §8.*

- [ ] **E2 ○ — Fold the codex0-learned gates into `bindery_preflight.py` / `imposition.py`.** Both already live in `engine/`. The book taught them creep, trim, duplex parity and collation lessons that are still expressed as book-side scripts (`build_punching_guide.py`, `build_press_sheet_map.py`, `check_vol3_folio_run.py`).

- [ ] **E3 ○ — Non-uniform label/spine-label geometry.** Direction doc **Q4**, still open: `sticker_sheet_manifest_v1` is a uniform grid (single `grid: [rows, cols]`, one `cell_size`), and the Codex 0 label contract needs a cover label plus three spine labels at different sizes with one rotated title. `tooling/build_cover_label_print_sheet.py` is the workaround.

- [ ] **E4 ○ — Duplex registration instrument.** `tooling/duplex_registration_instrument.tex` and the measured **+1.801 mm, sd 0.008 over 17 patches** calibration. A printer-calibration instrument is engine-general and has nothing to do with any book.

### Band F — Build identity and provenance

- [x] **F1 ★ — Build stamping and the build ledger.** *Now:* `build/stamp_colophon.py` (532 lines) + `build_ledger.yaml`. *Generalization:* a bound artifact claims a build number, stamps a git head into its colophon sources once, and **`--final` refuses a dirty tree by design** while a proof reports `-dirty` loudly rather than refusing. *And the gate that exists for exactly one failure mode:* PASS F / **CC14** — every volume of one build must carry a byte-identical stamp, because build 84 rendered body text from one tree state and apparatus from another and looked healthy. *Second consumer:* a keeper-capture book printed for review is worthless without knowing which tree state it shows. **High value, low blast radius, small code.** *PROMOTE, ruled 2026-09-28 (`RULINGS.md` 01a0e9ab-077c); done the same day — §8.*

- [x] **F2 ○ — Render evidence extension.** `schemas/render_evidence_v1.yaml` exists; extend it with `resource_roots.py`'s origin proof so evidence names which physical file supplied each logical reference. *Done 2026-09-30 with the raw-LaTeX precedence fix, as step 1 of the order ruled that day (`RULINGS.md` 01a0f458-a0ce) — §9.*

### Band G — The tenant split (P1/P2 execution)

- [x] **G1 ★ — Move content out of the profile tree. The mechanism landed; the content did not.** `engine/resource_roots.py` (302 lines) and manifest-owned asset precedence shipped on this branch (`dd891d5`, plan doc `2026-08-03_...`). The four ownership lanes exist. **And `profiles/40_latex_import/assets/codex0/` is still 307 MB / 39 tracked files** — the direction doc measured 194 MB on 2026-07-27; it grew. The engine can now be told where content lives; nobody has told it. *This is the highest-leverage item in the survey that requires no new design.* *PROMOTE, ruled 2026-09-28 (`RULINGS.md` 01a0e9ab-077c); done the same day — §8.*

- [ ] **G2 ○ — Profile package boundary.** Direction doc **Q3**, still open. A profile declares its asset dependencies without carrying them; tenant profiles (`codex0`, `mythic_letter_johannah`, the client brand set) resolve from outside the engine repo. `client_report` is the existing proof case that this can work — its assets are third-party property and can never enter this repo (direction doc §5). *This is the client/tenant split, and G1 is its precondition.*

- [ ] **G3 ○ — Repo split.** Explicitly future work per the direction doc §9. Listed only so it stays visibly downstream of G1/G2 and does not get attempted early.

---

## 4. What does **not** promote — tenant data, and it should get louder about it

These stay with the book. Naming them matters: A1 cannot move until it is cut along this line.

- The **beam-cut divider ritual** — `_generate_part_divider_recto_source`,
  `_generate_half_plate_verso_source`, the shared lighthouse leaf, the per-part reveal, the
  Part V ethereal payoff. This is the book's argument, not a mechanism.
- The **handwritten ask pages** — `_generate_ask_pages_source`, `_ask_page_count`, the R/V/R
  front block and the closing leaf.
- **Volume III's section roster** — `_vol3_section_titles()` is a hardcoded list of this
  book's apparatus.
- `_part_codex_register`, the `johannah` / `witness` / `archival` / `reader` edition names,
  the `cx0:` marker vocabulary (until C2), the purple axis, the whisper ornament ladder, the
  specific rail plant ladder, the endless-knot blank-leaf asset.
- All 307 MB under `profiles/40_latex_import/assets/codex0/` (see G1).

**A boundary case worth an explicit ruling, because it will come up in every candidate below
A1:** the *ritual* is tenant, but the *slot* is engine. "A part opens on a shared leaf whose
verso is a per-part plate" is a general divider grammar; "the leaf is a whitewashed lighthouse
with a beam-shaped die-cut" is Codex 0. Where each candidate's cut falls is the actual work of
promotion, and it is not mechanical.

---

## 5. Proposed sequencing

Ordered so that nothing is refactored twice. **Steps 0–2 ruled** (custody 2026-09-01; steps 1–2
on 2026-09-28: "starting with G1 and the small moves is right"). Steps 3 onward are not ruled,
and step 3 is already amended by the 2026-09-01 selector-first ruling (§7).

0. **Custody** — C-A, C-B. Before anything.
1. **G1** — content out of the profile tree. No new design, mechanism already shipped, and it
   unblocks every later move by making the engine repo something that can be reasoned about.
2. **A3, F1, E1** — the small, high-confidence, low-blast-radius promotions. Cheap proof that
   the promotion test works before betting A1 on it.
3. **A1** — the spine compiler, cut along the §4 line. The big one.
4. **A2** — selection manifests. Only meaningful once A1 is generic. **This is the step that
   first produces a keeper-capture PDF**, and the first one that should be evaluated by
   reading the output rather than by tests.
5. **B1, B2, B3** — volumes, label-harvest contents, pass orchestration. Wanted the moment a
   corpus book gets large, which will be immediately.
6. **D1, D2** — rails and the ornament law, once there is a second book to prove them against.
7. **C1, G2** — edition gating generalized, profile packages. Both touch client work; both
   want their own session.
8. Everything marked ○ that has not been pulled forward by then.

**Expect breakage, and expect it in Band A.** The book's compiler has never run against a
source set it did not author. The first keeper-capture render will fail on frontmatter
variance, missing `note_role`s, files with no headings, and heading depths the spine model has
never seen. That is the point of doing it — but it means step 4 should be scoped as a
*discovery* pass, not a delivery.

---

## 6. Ratification ledger

Open for the capability bands; closed for custody. **Keeper direction 2026-09-01 23:32
EDT:** "the codex 0 specific things are specific to it. I will have to rule on them in a new
session." Read as: the §4 tenant/engine cut stands as the frame, and bands A–G are ruled in
a dedicated session, not piecemeal — the merge to `main` happens first, "and then do the
refactoring work." The §7 amendment (selector before compiler) is not yet ruled either way.
For each candidate, Luis rules one of:

**PROMOTE** (move it, this cycle) · **CONTRACT** (write the contract now, move the code later)
· **HOLD** (real but not now) · **TENANT** (it does not promote; it is book data) · **DROP**.

| Band | Candidates | Ruled |
|---|---|---|
| Custody | C-A, C-B, C-C, C-D | all four ruled and done (2026-09-01/02) |
| A — composition | A1★ A2★ A3★ A4 A5 | A3 PROMOTE, done (2026-09-28); A2 built (2026-09-30, §10); rest — |
| B — multi-volume | B1★ B2★ B3★ B4 | B1, B2 built (2026-10-01, §11); B3 PROMOTE (2026-09-28): assertion half done — draft renders + `renders-agree` in the engine; the pass order stays in the book (one consumer = contract, not code). `2026-09-28_codex0_build_performance_plan.md` §5; rest — |
| C — edition gating | C1 C2 | — |
| D — furniture | D1★ D2★ D3 D4 D5 | — |
| E — physical | E1★ E2 E3 E4 | E1 PROMOTE, done (2026-09-28); rest — |
| F — build identity | F1★ F2 | F1 PROMOTE, done (2026-09-28); F2 done (2026-09-30, §9) |
| G — tenant split | G1★ G2 G3 | G1 PROMOTE, done (2026-09-28); G2, G3 — |

**On ratification this document is committed to `42_optical_foundry`** and the ruled set
becomes the port queue.

---

## 7. Proof render findings, 2026-09-01

**What was tried.** A review-instrument book composed from the capture corpus
using only shipped Foundry surfaces — `composite_bundle`, generic `section_dividers`, per-source
`chapter_opener`, `render.delivery: bound` with chapter running heads, the `keeper` profile —
run on Sol under system `python3`. Manifest:
`manifests/keeper_capture_book_2026-09-01.composite-bundle.yaml` (committed). Output:
`generated/keeper_capture_book_2026-09-01/` (not committed). The spine was hand-authored by a
throwaway generator kept beside the output; that generator is exactly the hole **A2** fills.

**Outcome.** LaTeX completed: **the whole book** in 1m35s, with a title page, a title-verso production colophon, a **linked Contents with page numbers**, month dividers, chapter running heads and outer folios — the review instrument works as a shape. The Foundry then **withheld the final PDF**: its fail-closed missing-character lint found **84 warnings across 13 code points** DejaVu lacks, in **47 of 301 files** (🕯 U+1F56F alone: 41 warnings / 35 files — it is the corpus's sign-off glyph; also ✓ ✔ ❌ ✅ ⏩ 🪐 🧬 🧠 🛡 and three CJK characters 斩 杀 线). There is no manifest key to downgrade that lint, and the emoji lane (`engine/emoji_substitution.py`) vendors exactly one glyph (⚠️). Evidence JSON therefore reads `status: error`, `pages: null`, and `render_metadata.success` is absent; the page count comes from the renderer's own error payload and `pdfinfo`. The compile-stage PDF is readable on disk at `generated/keeper_capture_book_2026-09-01/.keeper-capture-book-2026-09-01.compile-stage-f7e6b0624b6642ce95b76295b4c16095.pdf` (6.7 MB; 13 `[[OFDIV:…]]` furnish markers still in its text layer because final sanitization never ran; the keeper profile's DRAFT overlay is on).

**Three attempts to get a PDF; two engine gaps found on the way.**

| # | Attempt | Result | Finding |
|---|---|---|---|
| 1 | dividers + compiler wrapper headings, no `chapter_opener` | LaTeX: `Undefined control sequence \CodexPlateRitualBegin` | `_section_divider_start_lines` (`engine/manifest_compiler.py:717`) emits the codex0 plate-ritual mark unconditionally, but its `\providecommand` fallback (`:878`) is only written when some source carries a `chapter_opener`. **Any non-codex0 profile with `section_dividers` and no openers fails.** A 2026-08-12 book fix regressed the generic profile set — a **P3** violation, and the sharpest **§4 / G1** boundary case in the survey: tenant macro, engine path. |
| 2 | `chapter_opener` per source (suppresses wrapper headings; supplies the fallbacks) | LaTeX: `Undefined control sequence \st` | Two captures use `~~strikethrough~~`; pandoc lowers it to `\st{}` (`soul`). `keeper.tex`/`base.tex` carry no `$if(strikeout)$` block (pandoc's stock template does), and the manifest `variables:` allowlist has no `header-includes` ingress, so there is no manifest-side fix. Excluded both files for this proof. **Template gap for the whole document-spine family**, not a corpus defect. |
| 3 | as 2, minus the two strikeout files | LaTeX succeeded; **final PDF withheld** by the missing-character lint (84 warnings, 13 code points, 47 files) | Roadmap item `of-render-only-emoji-assets` is the blocker for *any* Atrium-corpus book: a corpus book cannot demand corpus-clean glyphs. Either the vendored-asset registry grows (the roadmap's own design) or a manifest lint policy reports instead of refusing. Also seen: with `numbersections` on and openers unnumbered, demoted body headings count up to `0.0.63.4.2` — the sampler manifest's "desired but not honored" `numbersections: false` is still not honored. | |

**Missing versus the ★ candidates.**

- **A2 ★ (selection manifests)** — confirmed absent and load-bearing: 2,200 lines of YAML had to be
  emitted by a script to say "every file in one directory, by `created`". Order fell back to the
  filename date for 1 file and to "undated" for 1 (`FRONTIERS.md`). The `note_role` variance the
  map predicted is real (40 distinct values across 303 files, including `keeper-capture`,
  `capture`, and `"capture"`), which is exactly what a predicate selector has to normalise.
- **A1 ★ (spine compiler)** — the generic compiler cannot strip a source's own `# h1` when it
  supplies the heading itself, so every chapter opens with its title twice (opener, then the
  demoted source h1 as `\subsubsection`). Five files open at h2 and sit one level off. The
  `numbering_strategy: section_dividers` path was unusable for multi-source parts: it demotes only
  the first source after a divider by one level and every other source by two
  (`manifest_compiler.py:1502-1508`), so a file's internal heading depth would depend on its
  position in the month.
- **A3 ★ (epigraph harvest)** — not exercised; no capture carries `epigraph_*` fields. Nothing blocked.
- **B1 ★ (volumes)** — One volume of that length is past any bindable extent (build 100's largest volume was 288 pages). The first real keeper-capture print needs volumes on day one, as the map predicted. Not attempted.
- **B2 ★ (linked contents)** — the contents is flat: one `\addcontentsline{subsection}` entry per source
  from the openers, no part entries, because a generic divider in `continuous` numbering emits no
  TOC line. Part-level contents needs either the (broken, above) `section_dividers` numbering or B2.
- **B3 ★ (pass orchestration)** — not needed for one volume; pandoc's own rerun handled the TOC.
- **D1 ★ (rails)** / **D2 ★ (ornament law)** — codex0-only; no rail or ornament vocabulary reaches
  the `keeper` profile. The review-instrument use (a rail per source or per beam) cannot be tried
  until D1 promotes.
- **E1 ★ (signature padding)** — not applicable to a perfect-bound proof; `_bind` twin not requested.
- **F1 ★ (build stamp)** — absent: the PDF carries no canon head. Its evidence JSON records source
  SHA-256s, which is the F1 raw material; the colophon line is the missing half.
- **G1 ★** — the divider failure above *is* G1's argument: content-specific macros are still
  reachable from the engine's generic paths.

**Smaller gaps met on the way.**

- `python3 -m cli validate` does not exist on this branch (README Quickstart lists it); the
  subcommands are `doc, manifest, profiles, smoke, initial, proof, impose`.
- README/INDEX paths still point at `~/Digital_Workspace/…`.
- Sol font fallbacks (Helvetica/Menlo → DejaVu) apply to the keeper profile as recorded on 2026-08-25.
- The three sub-lanes (`epistemics/`, `letters/`, `source_maps/`, 8 files) were left out; A2 needs a
  recursion rule.
- One capture embeds a relative `_attachments/…jpg`; `resource_roots` was pointed at the beam
  directory — it resolved (3 images in the compile-stage PDF), so `resource_roots` already covers beam-relative art.

**Keeper ruling on the glyph gate, 2026-09-01 23:32 EDT.** "The glyphs should grow to support
what is needed." The vendored-asset registry (`of-render-only-emoji-assets`) grows to cover what
the corpus actually uses — starting with the thirteen code points above — rather than a
manifest lint policy that reports instead of refusing. The fail-closed posture stays.

**Keeper ruling on the amendment below, 2026-09-01 23:44 EDT.** "Selector before spine compiler is
good. But ideally there would not be a spine compiler if possible. Manifest should be authoritative."
*Reading:* the amendment is accepted — A2 moves ahead of A1. And A1's target changes: the goal is
not to promote the 4,548-line spine compiler into the engine but to **dissolve it** — the selector
emits the bundle manifest directly, the manifest is the authoritative composition record, and the
spine as an intermediate artifact goes away where it can. Whatever of A1 survives is what a manifest
cannot express yet; that residue is what the ratification session should look at, not the compiler
as a unit. "Ideally … if possible" is the keeper's own grade: a direction with an escape hatch, not
an absolute.

**Suggested amendment to §5 sequencing.** Step 4 (A2) produced a PDF today without A1 moving —
the compiler's generic path is enough for a *flat* corpus book, and the failures were template and
macro-leak bugs, not spine-model failures. That argues for pulling **A2** ahead of **A1**: the
selector is small, has no codex0 dependency, and its first consumer is already waiting.

---

## 8. 2026-09-28 — the tag, G1, and the small moves

Ruled at 16:04 EDT (`RULINGS.md` `01a0e9ab-077c-7836-b986-8cb968ad2155`): tag the state that
renders Codex 0, then start the refactor at G1 and the small moves, across the Foundry and the
book's tooling in the Atrium.

### 8.1 The tag

`codex0-compatible-2026-09-28`, annotated, in both repositories: Foundry `aa3bd9e`, canon
`18926ac07` (which pins it). Pushed to deneb; not to GitHub, whose mirrors lag. The claim is
proved by a full three-volume build at that pair — run `of-refactor-baseline-aa3bd9e-2026-09-28`,
the regression lane (the book's `run_full_build.sh` with STEP 0 removed, so no build number is
claimed and no colophon is restamped) — which passed every gate: C3, D1c, D1d, G3, D2 plate
containment, E bind shapes (224 / 288 / 128 = 7, 9, 4 × 32), F one stamp.

### 8.2 What moved (Foundry `f424794`)

| Candidate | Engine surface | What stays with the book |
|---|---|---|
| **G1** | `profiles/40_latex_import/assets/codex0/` removed (39 files, 307 MB) and its `.gitattributes` LFS rule | the assets, under `codex0_v5/assets/codex0/v5/` (already the declared resource root) |
| **A3** | `engine/epigraph.py` (`epigraph_from_frontmatter`, `epigraph_from_file`); compiler `chapter_opener.epigraph_from: <path>` and `epigraph_from_source: true` | `_read_divider_epigraph` is now a wrapper naming the book's epigraph surface (`<chapter>/00_divider.md`) |
| **F1** | `engine/build_stamp.py` (`BuildLedger`, run-id guard, a new refusal to issue a number the ledger already records, scoped `git_head_short` with `-dirty` / `require_clean`, managed regions, `distinct_stamps`); CLI `stamps-agree` | `build/stamp_colophon.py` keeps which sources carry the stamp, the proof and final stamp lines, the registry block, and the spelled proof count |
| **E1** | `engine/bind_shape.py` (`pad_to_signature`, odd page count is an error, optional centred blank-leaf mark); CLI `bind-shape` | the endless-knot mark and its 0.2 width fraction, passed by `run_full_build.sh` PASS E |

The book's tooling imports the engine from the Foundry checkout named by `OPTICAL_FOUNDRY`
(exported by `run_full_build.sh` from `FOUNDRY`, which is now overridable), defaulting to the
canon submodule.

Equivalence before landing: the rewritten `stamp_colophon.py` wrote byte-identical ledger and
colophon files to the original in sandboxed runs (new run, idempotent re-run, `--notes`,
`--volumes single`, `--final`, `--dry-run`); the engine epigraph harvest matched the book's old
harvester on all 514 Markdown files in the book (76 carry epigraphs); book tooling tests 120 pass;
30 new engine tests pass.

### 8.3 Verification — by contact sheet

Candidate run `of-refactor-candidate-f424794-2026-09-28` (Foundry `f424794`, the book tooling as
refactored) passed every gate with the same shapes. Compared with the baseline by per-volume
contact sheet (reading and bind PDFs), page counts, bundle manifests and resolved sources:
everything identical except **one page, Volume I page 21 (folio 3), the Part I reveal plate**.

That page exposed a latent defect, not a regression. The manuscript's copy of the plate had been
revised on 2026-08-07, but the divider plate reaches LaTeX as a raw relative path resolved from
pandoc's working directory (the profile folder), so every build since — build 100 included — set
the profile's older copy, and resolution evidence (which records only tracked references) showed
nothing. G1 removed the shadow. Luis, 17:59: "The middle one was the one that I intended" (ruling
`01a0ea08-7757-7f0f-9176-4316debc18d6`); scar
`21_letters_and_creative/book/codex0_v5/structure/scar_codex0_part01_plate_revision_never_rendered_2026-09-28.md`.

### 8.4 Found on the way

- **The book's ledger held `next_build: 100` with build 100 already recorded** (hand-appended
  2026-08-15), so the next stamp would have reused 100. Luis, 16:23: "we can lift the permanent
  100 mark. the next build will be 101." (ruling `01a0e9b0-229b-71c2-8e4f-e4c7c45fd128`). Re-seeded
  to 101; the engine now refuses a recorded number.
- **Raw-LaTeX image paths bypass the resource-root chain** and are invisible in evidence. General,
  open; see the scar's remediation plan and the press note §5.
- **`codex0.tex` defaults three macros to book apparatus paths** (lines 172, 209, 382); the cause
  of three pre-existing `test_body_folio_start` failures. Same class, open.
- **Two builds must never run at once.** The spine compiler writes shared, non-run-scoped files
  into `codex0_v5/generated/volume_apparatus/`.
- **Six Client template tests fail on any fresh worktree**, because the client brand files are
  gitignored and exist only in the main checkout — the permanent-external constraint of the
  2026-07-27 direction note §5, visible in the suite.

### 8.5 Next

The build-performance plan (`2026-09-28_codex0_build_performance_plan.md`, ruling
`01a0e9c7-c01e-7d0a-bcc0-4793b00abce0`): step 1 (measure renders, parallel reading volumes), then
step 2 as the B3 promotion, then the image cache. Every other candidate in §3 is unruled.

## 9. 2026-09-30 — step 1: four defects and F2

Ruling `01a0f458-a0ce-7a10-a6b9-927a52a976cb` approved the order proposed on 2026-09-29 and
started step 1: the four open defects together with F2. Worked on branch
`dev/step1-defects-f2-20260930` in a worktree, verified, then fast-forwarded to `main`.

### 9.1 What changed

- **Raw-LaTeX image precedence, and F2.** A relative image path written as raw LaTeX was
  resolved by LaTeX itself, from the profile folder pandoc runs in, ahead of every manifest
  resource root, while the evidence named the manifest copy as the winner (the Part I plate
  scar). `engine/resource_roots.py` gains a pinning pass (`pin_render_resources`): before
  pandoc runs, the renderer rewrites every relative image reference it can see in the
  render-only source — the arguments of `\includegraphics`, `\OFSectionDividerBackground`,
  `\CodexFloatingPlate`, the rail and edge-ornament macros, `\OFImageInitialSetup`, the path
  argument of `\OFDecorativeImage`, and the template path variables in frontmatter — to the
  absolute path of its winner in the effective root chain. The file the evidence names is then
  the file LaTeX opens. Evidence gains `resource_resolution.raw_latex_pins`: per reference the
  pinned path, its origin, shadowed copies, and `latex_cwd_candidate`, the file LaTeX would have
  opened had the path stayed relative (the inversion, recorded, not only visible in pixels).
  References with no winner stay relative and name their LaTeX fallback. Schema updated.
- **Divider-only bundles compile and publish on every profile.** The chapter-opener fallback
  definitions are now emitted when a bundle has dividers, not only openers; the divider marker
  wrappers' fallbacks are the tagged, engine-guarded pair codex0 and base define (the old no-op
  fallbacks let the compile pass and then the final-PDF sanitizer failed closed).
- **Strikeout.** When pandoc, reading the source as the profile does, finds a Strikeout, the
  renderer includes pandoc's own package block (`lua-ul` under LuaTeX, else `soul`) as a header
  file; evidence records `render_metadata.strikeout_support`. A header file rather than
  metadata, because pandoc drops metadata `header-includes` whenever `--include-in-header` is
  also given (draft and baked renders give it).
- **`codex0.tex` apparatus defaults.** The template no longer names paths inside the Codex 0
  book. `codex_blank_leaf_ornament`, `codex_compass_field_icon` and `codex_folio_chip_asset`
  are allowlisted, path-guarded manifest variables; without them the blank leaf, compass field
  and folio chip draw nothing. The book's generator names its three files.

### 9.2 Verification

- Full suite: 600 pass, 7 fail — the seven known failures (profile checker local sources,
  ownvoice stacking, five client template contracts). The three `test_body_folio_start`
  failures carried since 2026-09-28 now pass: they were this defect — the codex0 profile could
  not render outside the book because its template named the book's endless-knot image.
- A real render reproduces the scar: with a different image at the same relative path in the
  pandoc working directory, the PDF embedded the profile folder's copy with pinning off and
  embeds the manifest's with it on.
- Whole-book regression (`CODEX0_REGRESSION=1`), baseline at `358d8d1` vs this branch: every
  gate passed; page counts 224 / 286 / 126 read, 224 / 288 / 128 bound, unchanged. The resolved
  sources differ exactly by the three apparatus variables and the tagged marker fallbacks.
  Pages: **16 per PDF MARKED, none failing** — every one is a blank leaf carrying the endless
  knot. Step 3's bake had never baked that image: its callback resolves a relative name through
  kpse or the working directory, and a path LaTeX finds only through `\graphicspath` missed the
  index. Pinned absolute, it is now baked, so it arrives in a Form XObject — the image-edge
  deviation ruling `01a0eb4f-849e` accepted and the comparison marks. Image data, placement,
  drawings and text are identical on all 16.
- Evidence: 24 / 34 / 9 references pinned per volume, none unpinned, no warnings, no profile
  shadow (none exist since G1).

### 9.3 Found on the way

- Pandoc drops metadata `header-includes` whenever `--include-in-header` is given. Draft and
  baked renders give it; any profile whose render relies on frontmatter `header-includes` and
  is rendered with `--draft` or `--bake-images` would lose them. Not observed to matter for
  Codex 0 (drafts agree with finals, PASS H); not investigated further.

## 10. 2026-09-30 — step 2: glyph growth and A2, and the first keeper-capture book

Step 2 of the order ruled that day (`01a0f458-a0ce`): the glyph-growth ruling of 2026-09-01
("The glyphs should grow to support what is needed") and A2 under the selector-first ruling of
the same night. Branch `dev/step2-glyphs-a2-20260930`, verified, fast-forwarded to `main`.
Scoped, as §5 said, as a discovery pass.

### 10.1 Glyph growth

- **`engine/glyph_registry.py`** and **`profiles/40_latex_import/assets/glyph_registry.json`**
  replace the one-entry table in `engine/emoji_substitution.py`. Three kinds of substitute:
  emoji → a vendored Noto Emoji image (v2.051 SVG, converted to vector PDF; Apache-2.0); CJK and
  kana → `OFFallbackCJK`, Noto Sans CJK (JP face) subset to exactly the registered characters;
  symbols the body face lacks but DejaVu Sans has (✓, ✔) → `OFFallbackSymbols`, DejaVu Sans
  subset. Fallback-font characters stay real, searchable text. The fail-closed lint is unchanged.
- **`python3 -m cli glyphs scan|grow <sources…>`** reports or vendors what a source set needs.
  A code point counts only when the faces the body is set in lack it (TeX-tree DejaVu Serif,
  Serif Bold, Sans, Sans Bold, intersected), so covered characters stay text.
- **Inline code.** A per-render pandoc Lua filter lowers registered glyphs inside code spans,
  only where the code face (DejaVu Sans Mono) lacks them. Code blocks are verbatim and untouched.
- **Grown for the capture corpus:** 11 emoji (🕯 🪐 🧠 ❌ ⏩ 🧬 🛡 ✅ 🎙 🖥 🔖),
  3 CJK (斩 杀 线), 2 symbols (✓ ✔). The thirteen code points of §7 are all covered.
- Known limit: a fallback character is set in its fallback face whatever the profile's own
  font covers (a ✓ in an Iowan document would set in DejaVu Sans). Codex 0's sources carry
  only the existing ⚠ seed and one ✅ in a placeholder.

### 10.2 A2 — selection manifests

- **`engine/selection.py`**, **`python3 -m cli select <file>`**. A `kind: selection` file names
  roots (with an explicit recursion rule), excludes, predicates (`kind`, `note_role`, `status`,
  `beam_home`, `tags_any`, `tags_all`, `created` window; compared normalized), order (`created`,
  `path`, `title`, `uid`; undated first/last; pins), grouping into dividers (`month`, `year`,
  `directory`, `none`, with title/subtitle templates), per-source defaults, and the bundle
  settings. It writes an ordinary `composite_bundle` manifest — the authoritative composition
  record — with a `selection:` block (selection file, its sha256, counts, date and title
  origins) and per-source `selection:` provenance. No spine.
- Dates: frontmatter `created`, else a date in the file name, else undated. Titles: the body's
  title heading (its first heading, if level 1; a kicker line above it is allowed), else
  frontmatter `title`, else the file name; Markdown emphasis is removed for the opener.
- **Two source keys in the bundle compiler**, both opt-in and set by the selector:
  `strip_leading_heading` removes the body's title heading when the chapter opener carries it
  (the "title twice" finding of §7); `strip_body_metadata_blocks` removes YAML blocks inside a
  body, which pandoc reads as document metadata in an assembled bundle (first render: one
  capture's legacy second frontmatter put `2025-12-06` on the book's title page). Counted in
  evidence as `body_metadata_blocks_removed`.

### 10.3 The first keeper-capture book

`manifests/keeper_capture_book.selection.yaml` → `manifests/keeper_capture_book.composite-bundle.yaml`
(the captures at the top level of the beam as on 2026-09-01, dated by `created`, `FRONTIERS.md`
undated; month dividers). Rendered on the keeper profile: **status ok, one very long volume,
about 3 minutes**, every glyph lint passing, contents and section numbering correct
(`numbersections: false` honoured). 154 emoji and 27 fallback-font characters substituted.
Looked at by raster: title page, contents, a month divider, chapter openers (emoji in titles and
running heads render; no doubled titles), CJK and check-mark pages.

Not yet right, for the next steps rather than this one:
- **One very long volume** — B1 (volumes) is needed before it can be printed, as predicted.
- **Long unbreakable paths in inline code** run past the right margin; the keeper template does
  not break `\texttt` at slashes.
- The safe-area overlay of the bindery preflight timed out on a book this long and crashed the
  CLI. Now a timeout is reported in the preflight record instead (`OF_PREFLIGHT_TIMEOUT_S`,
  default 120 s); the book's render still lacks a safe-area guide.
- The keeper profile prints its DRAFT watermark (profile behaviour).
- The sub-lanes `epistemics/`, `letters/`, `source_maps/` are out; including them is a line in
  the selection file, and a choice for the keeper.

### 10.4 Verification

- Full suite: 620 pass, 7 known failures (unchanged set). New: `tests/test_glyph_registry.py`,
  `tests/test_selection_manifests.py`, and a preflight-timeout test.
- Codex 0 whole-book regression, `of-step1-candidate-2026-09-30` vs `of-step2-candidate-2026-09-30`
  (`CODEX0_REGRESSION=1`, branch Foundry): every gate passes, **CLEAN** — every contact sheet
  identical, resolved sources and manifests identical. The book is untouched by this step.

---

## 11. 2026-10-01 — step 3: A1's residue, B1 and B2

Step 3 of the order (`RULINGS.md` 01a0f458-a0ce, amended by 01a0f8ba-4937), after the
architecture review's candidates 2, 1 and 4. Branch `dev/arch-review-20261001`.

### 11.1 A1 — what the spine tool still does that a manifest cannot say

The 2026-09-01 ruling turned A1 from "promote the spine compiler" into "dissolve it":
whatever survives is what a manifest cannot express yet. The spine tool
(`codex0_v5/tooling/spine_to_bundle_manifest.py`, 4,541 lines) already writes ordinary
bundle manifests, one per volume, so everything inside a volume is expressible. Its
functions fall into five groups:

| Group | Functions | Where it belongs |
|---|---|---|
| The book's ritual pages | `_generate_part_divider_recto_source`, `_generate_half_plate_verso_source`, `_spine_movement_index`, the plate and divider-poem uids, `_ask_page_count`, `_read_front_ask_epigraph`, `_generate_ask_pages_source`, `_part_codex_register`, `_vol3_section_titles` | **Tenant** (§4). Each writes a Markdown file that the manifest names as a divider `source:`; the manifest already expresses the result. |
| Choosing and naming sources | `load_spine`, `select_parts`, `_list_matter_files` and its front/back variants, `_source_uid`, `_read_divider_epigraph`, `_delivery_block`, `_declare_work_resource_root` | **Expressible**: A2 selection (§10), A3 (done), `render.delivery`, `resource_roots`. Missing in the selector: a per-root `role` (front and back matter directories). Small. |
| Volumes | `--volume`, `--body-folio-start`, `_select_volume_parts`, `_volume_body_source_paths`, the shell build's folio seating | **B1 — built**, §11.2. |
| Contents across volumes | `_pdf_part_pages`, `_page_footer_folios`, `_volume_locator_rows`, `_reading_volume_locator_rows`, `_generate_reading_volume_contents_source`, `_validate_grouped_toc_body` | **B2 — built**, §11.3, as the mechanism. The book's eleven-movement grouping and its typography stay tenant. |
| Not yet anywhere | `_harvest_volume_endnotes` + `_generate_vol3_notes_source` (**B4**); `_measure_sources_words` and friends (**A5**); the interior-plate strip and chip passes (source preparation — candidate 3, then D3) | Later items in the order. |

So after this step the residue of A1 is B4, A5, a selector `role`, and source
preparation. Codex 0 still builds through its own tool and shell passes, unchanged: moving
it onto the engine's volumes would change how it compiles, and the B3 ruling keeps its pass
order in the book. That move is now possible; it is not taken here.

### 11.2 B1 — volumes

A bundle manifest may carry `volumes:` — each volume an `id`, an optional `title` and
`subtitle`, and the source it starts before. `cli manifest` sees it and hands the manifest to
`engine/volumes.py`, which:

- cuts it into one ordinary bundle manifest per volume (its sources and their dividers, a
  `volume:` block, `-vol-<id>` bundle id, the volume title in the subtitle);
- renders them in order, each body starting at the folio after the previous volume's last
  **PDF page label**;
- seats the body on the right physical side when the layout is two-sided (an odd folio on an
  odd page: the parity law of `12ef7af`), inserting a blank leaf when the parities differ.

The seat is template behaviour. `codex0.tex` already seats `$body_folio_start$`, so a codex0
volume gets the variable. Every other template gets the engine's `\OFSeatBodyFolio` (in the
template contract) and roman-numbered front matter, so the body's arabic folios are the only
arabic labels in a volume. The selector can ask for volumes: `volumes: {count: N}` cuts at
group boundaries, balanced by text length, or a list names the group each volume starts at.

### 11.3 B2 — the contents of the work

With `render.work_contents` on, the first pass is rendered in draft. The engine reads each
volume's divider-page map (`<render_id>.divider_pages.json`, from the furnish marker) and turns
every divider's page into its PDF page label: folio authority is the label, never the printed
footer. The second pass gives every volume a **Contents of the Work** — each divider with its
volume and folio, linked when it is in that volume — in the front matter, ahead of the seated
body. The contents therefore cannot move a body folio. The second pass checks that anyway:
if any volume's first or last body folio, or any divider's folio, differs from the first pass,
the run fails. The run writes `<bundle_id>.volumes.json`.

### 11.4 The keeper-capture book in six volumes

`manifests/keeper_capture_book.selection.yaml` now asks for `volumes: {count: 6}` and the
contents of the work. The six-volume count is a starting point, not a ruling. Rendered on
2026-10-01 (12.5 min, both passes):

| Volume | Months | Pages | Folios |
|---|---|---|---|
| I | October–December 2025 | 305 | 1–299 |
| II | January–March 2026 | 308 | 300–602 |
| III | April–May 2026 | 370 | 603–966 |
| IV | June 2026 | 244 | 967–1204 |
| V | July 2026 | 177 | 1205–1375 |
| VI | August 2026 – undated | 300 | 1376–1668 |

13 contents rows; the contents moved no folio. Checked by eye: Volume II's title page,
colophon, contents, contents of the work and the first divider. Found and fixed: the contents
of the work carried the in-volume contents' running head. Not yet right: balancing by text
length is rough (Volume III is twice Volume V); the volumes render one after another (the
second pass could run in parallel, as Codex 0's final wave does).

### 11.5 Verification

`tests/test_volumes.py` covers the split, the validation of bad cuts, the two seats, the
selector's volumes and a two-volume render (continuous folios, roman front matter, parity,
contents). Full-suite and whole-book results are recorded in the session ledger.
