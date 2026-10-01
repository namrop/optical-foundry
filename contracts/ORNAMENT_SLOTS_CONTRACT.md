---
uid: 01a0f952-f2ee-7f75-86fb-c37e67445550
kind: note
note_role: contract
validation_profile: standard
status: current
created: 2026-10-01T17:20:00-04:00
updated: 2026-10-01T19:05:00-04:00
beam_home: 42_optical_foundry
title: "Ornament slots and rail art — Optical Foundry"
summary: "Draft engine contract for step 4 (D1, D2) of the order, written from the keeper's ruling 01a0f951-dc5d: the engine defines ornament slots and the rules each follows; a profile fills the ones it wants; rails, ornaments and their art come with the profile, which lives outside the engine repository by default; in the keeper-capture book a rail marks Luis's literal voice, and the book gets new rail art whose requirements are defined here first. Every rule is either carried from Codex 0 (with its source) or marked as a proposal for the keeper to rule on."
tags:
  - optical-foundry
  - contract
  - ornaments
  - rails
  - profile-package
author:
  name: Claude Opus 5.5
  harness: hermes-agent
  model: claude-opus-5-5
  provider: custom:primary
  voyage: "t3-code:hermes-acp"
  at: 2026-10-01T17:20:00-04:00
last_touched:
  name: Claude Opus 5.5
  harness: hermes-agent
  model: claude-opus-5-5
  provider: custom:primary
  voyage: "t3-code:hermes-acp"
  at: 2026-10-01T19:05:00-04:00
principal: luis
---

# Ornament slots and rail art — Optical Foundry

## Pith

The engine names the places a page can carry an ornament and the rules for each; a profile,
kept outside the engine repository, decides which places it fills, with what art, and what its
rails mean.

## Abstract

Luis, 2026-10-01 (ruling `01a0f951-dc5d`): "I think in the keeper book, rails should mark my
literal voice. We will make a new set of art for these rails, but we can define what needs to
be true of the art. there are many ornament slots that exist, they don't all need to be filled,
but there are rules about how each works. all of this comes with the profile. The rails and
ornaments are part of the profile, which should not be baked into the repo by default."

Luis answered the draft's open questions the same day (ruling `01a0f99a-b2db`): "1. yeah
marking in the source by "hand" is fine. 2. I think the profiles should be in their own repo.
we can point to it. This will allow me to make a repo with public profiles. 3. breath, hinge,
rails. I will deal with generating art for it later 4. do the same thing as codex 0. I can
tweak later. 5. yes it can tighten but not loosen".

This contract splits that into three parts: the **slots** the engine owns and their rules (§1),
the **art requirements** each slot imposes, rails in most detail (§2), and the **profile
package** that brings rails, ornaments and art from outside the engine (§3). §4 is what the
keeper-capture profile would declare. §5 lists what is open. Rules marked *Codex 0* are
already enforced for that book and are carried as the starting point; rules marked
*proposed* are new and wait on Luis.

## 1. Slots

A slot is engine-owned: its name, where it can land, and the rules that hold there. A profile
that leaves a slot empty gets nothing on the page and no error.

| Slot | What it is for | Where it may land | Rules |
|---|---|---|---|
| `rail` | Marks a run of one declared voice or register in the outer margin (D1). | Outer margin, beside the marked text only. | §1.1 |
| `whisper`, `breath`, `hinge` | Pauses between passages, in rising weight. | Between blocks. | Never at a page top: a page break already is the pause (*Codex 0*, ornament law, 2026-08-07). Weight ladder hinge > breath > whisper in height and in space around it (*Codex 0*, 2026-08-06). |
| `passage_rule` | A drawn rule between flowing sources. | Between sources. | As the pauses. |
| `tailpiece` | Closes a section. | After a section's last block. | Legal at a page foot and exempt at a page top; at most one structural ornament at a page foot, the first kept (*Codex 0*, "either/or"). |
| `threshold` | Opens a section, a door. | Before a section's first block. | As the tailpiece. Never removed at a page top: removing it removes meaning (*Codex 0*). |
| `edge_companion` | A small mark in the margin beside a passage. | Outer margin, within the printer-safe area. | Parity keyed to the page counter, not the physical count (*Codex 0*, rails contract). |
| `blank_leaf` | Sits on an intentionally blank page. | Centre of a blank page. | Only on pages the engine itself left blank. |
| `folio_chip` | Backs the page number. | Behind the folio. | The art's visual centre lands on the numeral's ink centre (*Codex 0*, folio chip measurement). |
| `divider_plate` | Full-page art on a divider. | A divider page. | Full bleed, oversized past trim by the bleed allowance (*Codex 0*, 2026-07-27). |
| `floating_plate` | Full-page art inside a chapter. | A page of its own inside the chapter it belongs to. | Contained in its chapter, re-proved on every render (*Codex 0*, D3). |
| `image_initial` | The art capital that opens a chapter. | First line of a chapter body. | Raised, on the baseline of its line (*Codex 0*, 2026-08-03). |
| `title_background` | Art behind the title page. | Title page. | Relative path to PNG/JPG/PDF only (engine guard). |

The **page-position law** (D2) is how the engine enforces the "where it may land" column: on
the shipped page, at output time, not predicted from the source (*Codex 0*, `e0bc6fd`). A
profile may tighten a slot's rule, never loosen it (ruling `01a0f99a-b2db`). A rule has two
parts, the page top (`keep` or `drop`) and the page foot (`keep_first` or `drop`), in that
order of strictness; the engine's defaults are the table above.

**Built** (2026-10-01): the law for whisper, breath, hinge, passage rule, tailpiece and
threshold (`engine/latex/of_ornament_law.lua`), and rails (§1.1). The other slots are named
here and refused if a profile fills them, until the engine places them.

### 1.1 Rail rules

Carried from `contracts/RAILS_CONTRACT.md` (*Codex 0*), with the book-specific parts removed:

1. **Continuity means identity of the marked voice.** One run per continuous stretch of that
   voice; not proximity, not page.
2. **A run never crosses a chapter or part boundary.**
3. **Interludes are transparent.** A pause ornament between two blocks of one run neither
   breaks it nor joins two runs.
4. **Every rail is a complete specimen, drawn natively at its length.** No stretching; a run
   longer than a page draws a separate specimen on each page.
5. **No rail beside unmarked text.** A rail is drawn only on pages a marked block occupies,
   for the extent it occupies there.
6. **No same-page duplicate** of one piece of art.
7. **Outer margin always**, parity keyed to the page counter; seated by balance between text
   and trim (*Codex 0*, 2026-08-06), and never crossing the trim line.
8. **Pagination-neutral.** Rails occupy no space; adding or reseating rails moves no folio.

## 2. Art requirements

What must be true of the art before a profile may wire it. The engine checks each one when a render
loads the profile and refuses art that fails, naming the file and the check
(`engine/ornaments.py`).

### 2.1 For every slot

- Transparent background (alpha), no ink on any border row of the canvas: the mark is
  **contained** (*Codex 0*, rail ladder).
- At least 300 dpi at the size it is placed (*Codex 0*, print floor).
- Provenance recorded beside each file: how it was made, from what (*Codex 0* practice).

### 2.2 Rails

- **Vertical and narrow**; verso/recto neutral, or supplied as a mirrored pair (*Codex 0*).
- **Aspect decides the length it can fill.** The profile sets the rail slot width (Codex 0:
  0.50in) and the line spacing; a piece fills a run of L lines only if its height-to-width
  ratio is at least `L × line height ÷ slot width`. Upscaling changes dpi, never aspect
  (*Codex 0*).
- **A ladder of lengths.** The set covers every run length the profile allows, from a
  shortest run (Codex 0: 2 lines) to a full page, in steps the profile chooses (Codex 0: every
  2 lines, 19 rungs). A run rounds **up** to the next rung.
- **Enough pieces per rung** that two rails on one page never need the same piece (Codex 0
  found three per rung collided about a third of the time without the walk-forward rule).
- **A family identity per run** (*Codex 0*: one run's separated blocks read as one botanical
  family); *proposed* for the keeper book: one family, since one voice is marked.

## 3. The profile package

Profiles live in their own repositories (ruling `01a0f99a-b2db`), and the engine is pointed
at them: `OF_PROFILE_PATH` (colon-separated), or one repository per line in
`~/.config/optical-foundry/profile_repos`. A package is `<repository>/<profile-id>/` and is
named in a manifest by its id, like any profile; an engine profile of the same id always wins.
The private repository on Sol is `optical-foundry-profiles`, beside the engine. It holds
(`engine/profile_package.py`, schema `profile_package_v1`):

- `profile.yaml` — the profile: the engine profile it extends, the defaults it adds, a
  template of its own if it has one, the source-preparation steps it uses (ruling
  `01a0f930-407c`), the slots it fills and what its rails mean (§3.1);
- the art for each filled slot, with its provenance;
- any template additions of its own.

The engine ships no ornament art and no rail meaning by default. Codex 0's are already outside
the engine in substance (`codex0_v5/`); its profile files and its 307 MB under
`profiles/40_latex_import/assets/codex0/` move into a package as G2, a later step of the order.

### 3.1 What a profile says its rails mean

A rail definition names the authoring mark that opens a run, how runs are told apart, and the
art ladder. Codex 0's: the `.codex-pataphorical` div, runs keyed by `story=`, the contained
purple ladder. The keeper-capture profile's: §4.

## 4. The keeper-capture profile

`optical-foundry-profiles/keeper-capture/`. It extends the engine's `keeper` profile and
renders with LuaLaTeX.

- **Rails mark Luis's literal voice** (ruling `01a0f951-dc5d`), marked by hand: a
  `::: literal-voice` div around the passage. Every marked passage in one capture is one run.
- **Slots filled:** rails, breath and hinge (`::: breath :::`, `::: hinge :::`).
- **Numbers:** Codex 0's (width 0.50in, line 0.18816in, shortest rail 4 lines, rungs every 2
  lines from 2 to 38, inner share 0.5), to be tuned.
- **Art:** to be made; until then the slots are declared and print nothing. The package's
  README states what the art must satisfy.

## 5. Answered

The five questions the draft left open were answered by ruling `01a0f99a-b2db` (quoted in the
abstract): marking by hand; profiles in their own repository; breath, hinge and rails; Codex 0's
numbers; tighten, never loosen.
