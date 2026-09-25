---
uid: 01a039a9-23fb-7c3d-aa95-b3f9ee3cb6c4
kind: note
note_role: architecture_note
validation_profile: standard
status: draft
created: 2026-08-25T12:05:00-04:00
updated: 2026-09-02T00:09:00-04:00
beam_home: 42_optical_foundry
title: "Codex 0 → Optical Foundry — capability promotion map (post-delivery)"
tags:
  - optical-foundry
  - codex0
  - promotion
  - architecture
  - decision-survey
  - ratification-open
  - proof-render
summary: "Post-delivery survey answering open question 7 of the 2026-07-27 architecture direction: which capabilities filter up out of codex0, and what the promotion test is. Adds a second driver the direction doc did not have — arbitrary-Atrium-corpus books (keeper captures, convergence logs) as a review instrument, not only a print target. 25 candidates in seven bands, each with its current home, its generalization, a non-codex0 use case, and blast radius. Also records the custody audit of the delivered copy: everything that made the book is committed, and almost none of it is pushed. Ratification ledger open — no candidate is ruled. §7 (2026-09-01) records the first keeper-capture proof render: compiled, final PDF withheld by the glyph lint, two engine gaps found."
principal: luis
---

# Codex 0 → Optical Foundry — capability promotion map

**Status: survey, open for ratification. Nothing here is ruled.**

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

- [ ] **A2 ★ — Selection manifests (query-driven source sets). NEW, not a promotion.** *Now:* does not exist. Codex 0's spine is 682 lines of hand-authored YAML naming every file. *Wanted:* select sources by predicate — beam + `note_role` + tag + date range + status — and order them (chronological by `created`, by beam, by uid, by explicit override), emitting a spine A1 then compiles. *Second consumer:* this **is** the keeper-capture book; there is no other way to build it. *Note:* this is the one candidate that is genuinely new construction rather than relocation, and it is the gate on the whole new-use-case.

- [ ] **A3 ★ — Frontmatter-driven epigraph harvest + layered attribution grammar.** *Now:* split — harvest in `spine_to_bundle_manifest.py::_read_divider_epigraph`, lowering in `engine/manifest_compiler.py` (`_inline_chapter_opener_epigraph_lines`), typography in `codex0.tex` (`\CodexOpenerEpigraph`, ratified 2026-07-28), with a generic `\OFChapterOpenerEpigraph` fallback already present. *Generalization:* any Atrium file may carry `epigraph_*` fields; the engine harvests them; the profile decides how they set. The layered model — dramatic line (speaker/context) over bibliographic line (author/source/translator/date), with `epigraph_register` inverting upright/italic — is already general, and its hardest-won rule (**`epigraph_date` means when the work was authored, which is why the translator slot exists**) is a corpus rule, not a book rule. *Blast radius:* low; the fallback macro already exists. **Closest to ready of anything in this survey.**

- [ ] **A4 ○ — Deterministic source UIDs and provenance comment.** `_source_uid`, `_provenance_comment`. Stable identity for a composed source, derived from its position; the manifest carries a comment naming spine, edition, parts, delivery mode. Generic. *Second consumer:* every composed document.

- [ ] **A5 ○ — Extent measurement.** `_measure_sources_words`, `_round_words`, `words_to_english`. Word extent of a source set, and its rendering as English prose for a colophon. Generic and small.

### Band B — Multi-volume and cross-reference machinery

- [ ] **B1 ★ — Volume splitting with continuous folio seating.** *Now:* `--volume {I,II,III}` + `--body-folio-start` in the book tooling, plus the **physical-sheet parity law** (`12ef7af`, print-critical: folio parity must match physical parity or `twoside` puts the outer rail in the gutter — build 45/46 shipped that defect and it looked fine on screen). *Generalization:* one logical document, N physical volumes, one continuous folio run. *Second consumer:* a keeper-capture corpus is large enough to want volumes on the first try.

- [ ] **B2 ★ — Linked contents via PDF page-label harvest.** *Now:* `_pdf_part_pages`, `_page_footer_folios`, `_volume_locator_rows`, `_reading_volume_locator_rows`. *The doctrine, and it is the reusable part:* **folio authority is PDF page labels, not printed footers.** Printed-folio scraping undercounts every time a volume ends on suppressed leaves — plates and trailing blanks own a folio and print none. Build 56 seated Vol II at a duplicate folio because of exactly this. Label arithmetic on both sides agrees by construction. *Second consumer:* any multi-file bound corpus wants a real contents.

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

- [ ] **E1 ★ — Signature padding to bind shape.** *Now:* `run_full_build.sh` PASS E. *Generalization:* pad a rendered PDF to a whole signature, emit a `_bind.pdf` beside the reading artifact, and hard-error on an **odd** rendered page count (a final leaf with no verso cannot be folded — do not let the pad absorb it). *Also generic:* pad leaves carry the ruled blank-leaf mark, because a bound-in blank with a mark reads as deliberate at collation and a bare blank reads as a printing error. The *choice* of mark is tenant data; the rule is not.

- [ ] **E2 ○ — Fold the codex0-learned gates into `bindery_preflight.py` / `imposition.py`.** Both already live in `engine/`. The book taught them creep, trim, duplex parity and collation lessons that are still expressed as book-side scripts (`build_punching_guide.py`, `build_press_sheet_map.py`, `check_vol3_folio_run.py`).

- [ ] **E3 ○ — Non-uniform label/spine-label geometry.** Direction doc **Q4**, still open: `sticker_sheet_manifest_v1` is a uniform grid (single `grid: [rows, cols]`, one `cell_size`), and the Codex 0 label contract needs a cover label plus three spine labels at different sizes with one rotated title. `tooling/build_cover_label_print_sheet.py` is the workaround.

- [ ] **E4 ○ — Duplex registration instrument.** `tooling/duplex_registration_instrument.tex` and the measured **+1.801 mm, sd 0.008 over 17 patches** calibration. A printer-calibration instrument is engine-general and has nothing to do with any book.

### Band F — Build identity and provenance

- [ ] **F1 ★ — Build stamping and the build ledger.** *Now:* `build/stamp_colophon.py` (532 lines) + `build_ledger.yaml`. *Generalization:* a bound artifact claims a build number, stamps a git head into its colophon sources once, and **`--final` refuses a dirty tree by design** while a proof reports `-dirty` loudly rather than refusing. *And the gate that exists for exactly one failure mode:* PASS F / **CC14** — every volume of one build must carry a byte-identical stamp, because build 84 rendered body text from one tree state and apparatus from another and looked healthy. *Second consumer:* a keeper-capture book printed for review is worthless without knowing which tree state it shows. **High value, low blast radius, small code.**

- [ ] **F2 ○ — Render evidence extension.** `schemas/render_evidence_v1.yaml` exists; extend it with `resource_roots.py`'s origin proof so evidence names which physical file supplied each logical reference.

### Band G — The tenant split (P1/P2 execution)

- [ ] **G1 ★ — Move content out of the profile tree. The mechanism landed; the content did not.** `engine/resource_roots.py` (302 lines) and manifest-owned asset precedence shipped on this branch (`dd891d5`, plan doc `2026-08-03_...`). The four ownership lanes exist. **And `profiles/40_latex_import/assets/codex0/` is still 307 MB / 39 tracked files** — the direction doc measured 194 MB on 2026-07-27; it grew. The engine can now be told where content lives; nobody has told it. *This is the highest-leverage item in the survey that requires no new design.*

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

Not ruled. Ordered so that nothing is refactored twice.

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
| A — composition | A1★ A2★ A3★ A4 A5 | — |
| B — multi-volume | B1★ B2★ B3★ B4 | — |
| C — edition gating | C1 C2 | — |
| D — furniture | D1★ D2★ D3 D4 D5 | — |
| E — physical | E1★ E2 E3 E4 | — |
| F — build identity | F1★ F2 | — |
| G — tenant split | G1★ G2 G3 | — |

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
