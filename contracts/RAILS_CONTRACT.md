---
uid: 019fc5d5-15c0-7e59-a091-9ad9d895fa9b
title: Pataphorical Register Rails Contract — Optical Foundry
status: current
updated: 2026-08-03
---

# Pataphorical Register Rails Contract — Optical Foundry

## Purpose

A **rail** is the outer-margin botanical mark that tells a Codex 0 reader "the register
changed here" — the margin channel of the book's purple authorship axis. It is a *register
marker*, not decoration. That single sentence generates almost every rule below: a rail must
appear beside pataphorical prose, must never appear beside literal prose, and must be legible
as one continuous voice while a story lasts.

This contract binds three things that were built separately and must now agree: the **contained
ladder** (what art exists and at what length), **story runs** (which blocks belong to one
voice), and **placement geometry** (where the mark lands on the page).

## Doctrine

Luis, verbatim (2026-08-02):

> "one set of rails per pataphorical story. so if it's my story vs johannah's there should be
> a break. jumping between my fields is not enough. a hinge or breath ornament is not enough
> either."

And, ruling the grammar to a single topology (2026-08-02):

> "let's not worry about multi-page spans. all of the generations should be contained.
> multi-page will just use distinct images."

Consequences, stated as rules:

1. **Rail continuity means story identity.** Not proximity, not chapter, not page.
2. **Ornaments and literal interludes are transparent both ways.** A breath or a hinge between
   two blocks of one story neither breaks the story nor joins two different ones.
3. **Every rail is a complete plant**, finite at both ends, drawn natively at its length. No
   stem stretching. A multi-page passage draws a *distinct specimen per page*, never one stem
   continued across a spread.

Canon sources: `21_letters_and_creative/book/codex0_v5/structure/canto0_rails_story_break_audit_2026-08-02.md`
(story-break audit + handoff), `.../structure/codex0_v5_purple_axis_doctrine_2026-07-18.md`,
`.../projection_maps/codex0_v5_pataphor_rail_semantic_boundaries_bookwide_2026-07-28.md`,
and the pool README at
`21_letters_and_creative/book/codex0/assets/generated_media/ornament_pool/rail_contained_ladder_2026-08-02/README.md`.

## Authoring surface

One fenced Div, wrapping unchanged prose:

```markdown
::: {.codex-pataphorical story="boy"}
Existing prose, unchanged.
:::
```

- `story=` is **required**. An untagged div emits a loud filter warning and falls back to its
  own isolated run — it will render, but it silently loses story continuity, so the warning
  must be treated as an error in review.
- Current story vocabulary (census 2026-08-06: 104 divs across 71 files, post gradient-band de-rails and breath-merge sweep; originally 125/69 at canon `bf0846339`):
  `boy` (67), `girl` (23), `both` (22), `realm` (7), `keeper-mythos` (6).
- `register="pataphorical"` is inert for rails. It survives only for the edition preprocessor's
  `_wrap_register` path (see *Edition interaction*).
- No folio is ever hand-authored. Placement is derived entirely from where prose lands.

## The two identities

This is the core of the model. Each div carries **two** integers with different jobs:

| id | Granularity | Job |
|---|---|---|
| **seg id** | one per div, globally unique | **Draw extent.** Owns its own `zref` begin/end labels. The shipout hook iterates *segments*, so a rail is drawn only on pages that div actually occupies. |
| **run id** | one per story run | **Seed / family key.** Feeds `\codex_rail_select_seed:n` (`run * 37 + …`), so a story's physically separated blocks read as one botanical family. |

`\CodexPataphorBegin{seg}{run}` / `\CodexPataphorEnd{seg}{run}`; the seg→run map lives in
`\g_codex_seg_run_prop`.

**Why both.** The first implementation used the run *hull* — `[first-start, last-end]` — and
painted the literal interludes between two blocks of one story as pataphor (caught by Luis on
Apertures: ~138 prose lines, only 14 pataphorical, hull railed pp.60–66 continuously). A
register marker must never make that claim. Hence: **run for family, seg for extent.**

## Run formation

A run is a maximal sequence of consecutive `.codex-pataphorical` divs sharing `story=`.

- Same story, consecutive → **same run**.
- Story changes → **new run**.
- A story *returns* after another story → **new run** (fresh id; runs are not rejoined).
- A chapter opener (`\OFSetRunningTagline`) or part divider (`\OFSetRunningDivision`) **resets
  run state**. A run can never cross a chapter or part boundary.
- Untagged div → its own run, plus a warning.

Observed Vol I (johannah): **40 divs → 21 runs** (11 single-segment, 6 pairs, 1 triple, 2
quads, 1 six-segment run), zero rail bleed across all 37 chapter/part boundaries.

## Selection — the contained ladder

Rails are chosen by **measured length**, from a 19-rung ladder at 2-line spacing (2L…38L).

- The role is fixed to the constant `contained`. Head/tail/body endpoint roles are retired
  from selection and survive only as ID-addressable provenance.
- Rung geometry: at the ratified `rail_width = 0.50in`, an asset fills rung `L` only if

  ```
  aspect >= (L * baselineskip) / rail_width
  ```

  Otherwise it would exceed the rail slot and be width-capped into a short rail. **Aspect
  decides the rung; upscaling changes dpi, never aspect.**
- The measured segment therefore rounds **UP** to the next rung, guaranteeing the chosen asset
  is at least as slender as the slot needs.
- Every wired asset must be **contained**: no ink on any canvas border row. Edge-touching
  families (`G*` gap-fill, `RX*` XL probes, `S38*` open/open integrals) are excluded by
  construction.
- Allocation of record: `rail_contained_ladder_2026-08-02/manifests/ladder_allocation.json`.

## Placement geometry

- Width is pinned at `\g_codex_rail_width_dim` (0.50in); the asset is scaled to the measured
  segment **height**, so width floats at or under the slot.
- **Fore-edge parity must key off `\value{page}`** — the same counter LaTeX uses to select
  `\oddsidemargin` vs `\evensidemargin` — **never `abspage`**. The two coincide only while the
  frontmatter page count keeps them in step; a single added front leaf desyncs them and throws
  every rail into the gutter. (Observed 2026-08-02 when the Edition Notice spilled to a second
  page.)
- The 2.5 mm inward `\marginparsep` shift is a composition/printer-safety inset, held on both
  parities.

## Invariants

These are the properties a build must not violate. Each is cheaply checkable from the PDF.

1. **No rail beside literal prose.** Rails appear only on pages a real div occupies.
2. **No rail exceeds the 0.50in slot.** Measured placed width ≤ ~0.51in (rounding slack).
3. **No same-page duplicate.** Two divs landing on one physical page must not draw the same
   asset. Enforced by `\g_codex_rail_page_used_seq`, which records paths placed on the current
   page and walks the pool forward on collision (cleared per shipout pass). Without it, a
   3-deep rung pool collides roughly a third of the time.
4. **No run crosses a chapter or part boundary.**
5. **Every div carries `story=`** — zero filter warnings.
6. **Struck assets never appear.** Currently: `v2-hinge-HN10` (the foliate spray), `RS01`,
   `H32D` (morphology failures).

## Reviewing rail breaks — gap vs. deliberate

A rail "breaking where it shouldn't" is almost always **markup coverage, not machinery**.
Per-segment drawing refuses to rail prose outside a div, by design (the Apertures ruling). So
the question is never "why did the rail stop" but "should that prose have been inside the div".

Structural detection is cheap: find a `CLOSE` followed by an `OPEN` of the **same story** with
prose in between. That finds candidates. It does not decide them — register is authorial.

**Sweep the EDITION-RESOLVED source, never the raw markdown.** Raw sources carry every
edition's text simultaneously (archival base plus each `cx0:edition` override), so a raw sweep
reports the archival base as unrailed prose even when the rendered edition gets a railed
override instead — and symmetrically it will miss real gaps that live inside an override. Run
against `generated/<run>/vol*/‹id›.codex_edition.md`, which is exactly what the filter sees.

Worked example (2026-08-03): a chapter with an edition variant. Raw source shows a
12-paragraph unrailed literal stretch (a bus station, a borrowed coat, a timetable) and a
raw sweep flags it as a gap. In the rendered edition that text never appears — a
`cx0:edition` override supplies a `.codex-pataphorical` retelling
("the tide had sent for him"), which is railed. The gap was an artefact of
reading the wrong file. Scope matters too: a raw two-part scan found 7 candidates; the resolved
whole-volume sweep found 22.

Parser note: strip `<!-- … -->` and ` ```{=latex} … ``` ` blocks, and do not count horizontal
rules (`---`) as prose, or they surface as phantom one-paragraph gaps.

**Read the whole paragraph. Do not rule from an opening phrase.**

This is written as a warning because the 2026-08-03 sweep got it wrong exactly that way. Two
gaps in one chapter open *"Spoken plainly, it is this…"* and *"said more plainly than I
could say it then"*, and were ruled deliberate literal breaks on the strength of those phrases.
Luis rejected the ruling and was right: read to the end and both are plainly pataphorical —
each carries the chapter's governing metaphor on (a lighthouse: its **lamp**, its **keeper's
log**, the **tide** it watches), and one carries a `.codex-heartword` span. Both were merged.

**"Spoken plainly" is not a register cue.** In this book it is a rhetorical move *inside* the
voice — contrasting with how a thing was said before, not stepping out of the register. Treat
any opening-phrase heuristic as unreliable.

**The distinction that actually holds — scene vs. reflection.** Confirmed against two correct
cases and two incorrect ones:

- **Deliberate break:** the unrailed prose narrates **concrete events or artifacts** — a scene,
  a receipt, a date, a quotation. A chapter may alternate a railed storm *frame* with
  unrailed *scene*: the frame closes, a plain scene at a ticket counter runs unrailed, then
  the storm frame resumes railed. This is the book's compressed-frame-plus-artifact
  structure and it is correct.
- **Genuine gap:** the unrailed prose **continues the reflective voice** with no scene and no
  artifact — *"And there was one more lesson…"* directly after
  *"And past all of that…"*, same person, same enumeration.

Supporting evidence for a genuine gap: the governing metaphor carried across it (lamp, log,
tide).

**A `.codex-heartword` or `.codex-signal` span in the unrailed prose proves nothing.** It was
briefly treated as evidence a field should continue; the ticket-counter scene disproves that —
it carries a `.codex-heartword` span and is correctly unrailed. Inline spans occur freely in
literal prose.

Other structural cues seen so far: a **verbatim quotation** (a ruled reality-break) and an
**image plate** in the gap.

Ornaments do not decide this either way: a `cx0:breath` or `cx0:hinge` may sit **inside** a div
(Afflicted Wizard line 45 predates this contract and does exactly that). If two divs of one
story are separated only by an ornament, merging them into a single field with the ornament
inside is legitimate and yields one continuous rail.

## Edition interaction

The edition preprocessor (`engine/codex_editions.py`) resolves `cx0:variant` / `cx0:edition`
**before** pandoc, so the Lua filter only ever sees edition-resolved text and computes runs
per edition. This is correct: each edition is its own coherent arrangement.

Two consequences worth stating:

- **Dropping a div in one edition can merge its neighbours' runs** (they become consecutive
  and same-story). Run ids, and therefore seeds and species, differ between editions. This is
  intended, and predates story runs — the old per-div counter shifted the same way.
- **KNOWN GAP: `_wrap_register` does not carry `story=`.** When an edition swap sets
  `register="pataphorical"`, the preprocessor emits
  `::: {.codex-pataphorical register="pataphorical"}` with no story attribute, so that block
  becomes an untagged div — warning, isolated run, story family broken. As of 2026-08-03 there
  is exactly **one** such marker in canon and it lives under an `archive/` path referenced by
  no live bundle, so the gap is dormant. Fix before using that mechanism on a live passage;
  it requires the variant marker to be able to declare a story.

## RULED: species varies within a run — this is intended, do not "fix" it

A run shares one seed, but the seed indexes into the **rung's** pool, and pools are ordered
closest-aspect-fit, species-agnostic. Index *k* is therefore a different species at every rung:

| rung | index 1 | index 2 | index 3 |
|---|---|---|---|
| 6L | spotted knapweed | iris versicolor | scabiosa |
| 10L | verbena | allium | harebell |
| 14L | salvia | balloon flower | dame's rocket |
| 22L | cow vetch | dame's rocket | spike speedwell |
| 38L | purple loosestrife | — | English lavender |

So a story whose blocks differ in length reads as knapweed-then-verbena rather than one plant
repeated. 10 of Vol I's 21 runs are multi-segment, so this is the common case.

**This was raised as a limitation and Luis ruled it is not one (2026-08-03):**

> "I don't actually want each run to have only one species. variety is good. if I change it, I
> will make species pools per story or something like that. but it seems like too much
> complexity that won't be understood."

Read the doctrine precisely: **"one set of rails per pataphorical story" governs where rails
BREAK, not what species fills them.** Story identity decides continuity — where a run starts
and ends, and that ornaments and literal interludes never break or merge one. Within a run,
botanical variety is wanted. The run seed makes selection *deterministic and story-derived*;
it was never meant to make it uniform.

**Do not re-solve the ladder species-major.** That option was considered and rejected as
complexity the book would not repay. The alternative Luis named — species pools scoped per
story — is likewise parked for the same reason. If either is ever reopened it needs a fresh
ruling, not an inference from the word "family."

(The word "family" in *The two identities* means a deterministic seed lineage, not a shared
species. Historical usage; kept because the code comments say it.)

## Tests of record

`tests/test_codex0_composition_filter.py`:

- `test_codex_pataphorical_blocks_emit_page_ranges_and_role_length_pools` — contained-only
  emission, the 19 rungs, retired roles absent, struck assets absent.
- `test_codex_pataphorical_same_story_divs_share_a_run_but_draw_as_separate_segments` — the
  run/seg split; guards against hull-painting.
- `test_codex_pataphorical_story_change_starts_a_new_run`
- `test_codex_pataphorical_run_resets_at_a_chapter_opener`
- `test_codex_pataphorical_run_resets_at_a_part_divider`
- `test_codex_pataphorical_untagged_div_falls_back_to_its_own_run`
- `test_codex0_template_wires_pataphor_ranges_to_page_local_role_rails` — fore-edge parity on
  `\value{page}`, abspage form absent, round-up rung selection.

Template-text assertions cannot catch an expl3 error. **Smoke-compile the rail machinery**
(two same-page divs through pandoc → lualatex with the codex0 profile) before trusting a change
to `codex0.tex`.

## History

- 2026-07-18 — purple axis; rails as the margin channel.
- 2026-07-27 — length ladder; Tier XL closed on a 300 dpi floor.
- 2026-08-01 — measured node-rich compositor (`failed/codex0-rail-compositor-20260801`);
  rejected: it satisfied length by *stretching* declared bare stems (151 of 207 occurrences in
  build 31), which Luis ruled an artefact.
- 2026-08-02 — contained ladder replaces it: 64 generations, 19 rungs, native length, Venice 2x
  to buy dpi (which reopened Tier XL — length was never the wall, dpi was). Fore-edge parity
  fixed to `\value{page}`. Same-page exclusion added. `v2-hinge-HN10` struck.
- 2026-08-02 — story runs (`dec2e6d`) + per-segment drawing (`c7c1b39`).
- 2026-08-03 — build 34: 209 placements, 55 distinct assets, 0 same-page duplicates,
  40 divs → 21 runs in Vol I.
