---
uid: 019fc640-8576-72e2-9f70-950b1e51d6d9
title: Chapter Opener Typography Contract — Optical Foundry
status: current
updated: 2026-08-03
---

# Chapter Opener Typography Contract — Optical Foundry

## Purpose

What a Codex 0 chapter opening is made of, and why each piece is shaped the way it is: the
title and rule, the epigraph and its layered attribution, the gap beneath it, and the raised
capital that starts the prose.

Companion to `RAILS_CONTRACT.md`. The two interact — see *The rail marker collision* below,
which is the reason 32 chapters silently had no capital at all.

## Anatomy

```
                 The First Rooms          <- \OFChapterOpener{title}
                 ─────────                   short centred rule

    The lamp was lit before anyone came home.   <- epigraph, italic
              — A. Correspondent · a postcard · March 3, 2024
                                                   layered attribution
                 (gap: \CodexEpigraphToBodyGap)
𝒯 HE first room was not a room I remember.   <- raised capital + small caps
```

Two epigraph macros exist and they are **not** equally live:

| macro | args | uses in Vol I |
|---|---|---|
| `\CodexOpenerEpigraph` | 7 (register, text, speaker, occasion, hand, work, date) | **34** |
| `\OFChapterOpenerEpigraph` | 2 (title, epigraph) | 1 |

`\CodexOpenerEpigraph` is the live path — the layered attribution grammar ratified 2026-07-28.
A change made only to `\OFChapterOpenerEpigraph` reaches essentially nothing; that mistake was
made on 2026-08-03 and cost a render. **Both now share `\CodexEpigraphToBodyGap` so they cannot
drift apart.**

## The epigraph-to-body gap

`\CodexEpigraphToBodyGap` = `2.2em`, up from `0.95em`.

Luis, 2026-08-03: *"I want something between the epigraph and the chapter text ... whitespace
for now is fine."* Previously an epigraph sat as close to the prose as a bare rule does, so the
attribution and the opening line ran together.

It is **one named hook, not an inline `\vspace`**, precisely because "for now" implies an
ornament may replace it. To put a mark there, redefine this command; nothing else moves.

## Raised capitals (not drop caps)

Luis-ruled 2026-08-03: *"can we make them raised caps instead? set them to the baseline of the
same line, so they read as a Large capital instead of dropped into the text."*

`\lettrine` is no longer used. The capital sits **on the first line's baseline** and rises above
it. There is no drop, so `findent`/`nindent` are gone with it.

`\CodexLettrine{L}{rest}` keeps its name and signature so `codex0_composition.lua` needs no
change — only the geometry underneath it changed.

### Geometry, measured not guessed

All values come from `MeaCulpa-Regular.ttf` (the `\headerfont`), read directly out of `hmtx`
and `glyf`.

1. **Left spill → margin intrusion.** Luis: *"the drop cap is shifting into the margin. this is
   wrong."* Several caps have a **negative left side bearing**, so ink begins left of the
   origin: `B` and `N` by 0.323em, `A` 0.215em, `Y` 0.078em. Anchored at the text-block edge,
   that ink lands in the margin. Each cap is kerned **right** by exactly its spill
   (`\CodexCapLeft@<letter>`, tabulated for all 26).

2. **Right overhang is deliberately NOT cleared.** As a *drop* cap the swash crossed the
   following letters at their own height and had to be kerned past — that was the visible
   defect, `T` striking through "HIS". Raised onto the baseline, the swash arcs **above** the
   following small caps and never meets them, so the clearance became pure wasted space.
   Verified by render across `T F W Y N I O B`.

3. **−0.05em nudge**, per Luis: *"nudge them closer by about 0.05 em across the board."*

4. **Not `\smash`-ed.** Smashing lets the descenders on `B N Y O` strike through line 2 — the
   same collision the old `nindent` existed to prevent. Unsmashed, the glyph reserves its
   depth; a further **0.12em** of declared depth guarantees line 2 clears the tail.

5. **Scale** is one hook, `\CodexRaisedCapScale` = `2.4`. Cap heights run 0.73–0.86em, so 2.4×
   body sets the capital at roughly two lines tall.

**If the header face ever changes, re-measure.** Every number above is font-specific.

### Colour

`\CodexLettrine` forces `LetterBody`. `\CodexLettrineInherit` is geometrically identical but
omits the forced colour so the ambient colour shows through — used when the opening words sit
inside a colour span (`.codex-signal` → `\CodexSignal` → `LetterAccent`). Luis-ruled 2026-08-03:
the cap takes the span's accent so the opening reads as one unit. Live case: The Door Standing
Open, *"You kept the lamp lit, and it held."*

## Which paragraph gets the capital

Decided in `codex0_composition.lua`. The opener is detected by `\OFSetRunningTagline`, **not**
`\OFChapterOpener` — pandoc's `latex_macros` extension expands the `\providecommand` fallbacks
before filters run, so the literal `\OFChapterOpener` string never reaches the AST.

Then, per Luis's rulings of 2026-08-03:

- **Epigraph blockquote opener** → skip the quote, letter the first prose paragraph beneath it.
  An epigraph must not cost a chapter its capital. (How to Receive This, The Peaceable Kingdom.)
  Implemented in **two** places that must agree — the top-level `Blocks` walker and
  `codex_lettrine_first_para` for Div-nested openers.
- **Verse / line block opener** → **no capital**. A lettered poem reads wrong. Hard stop.
  (Now / Later / Snap.)
- **Heading opener** → no capital.

### THE RAIL MARKER COLLISION

**This is the one that hid for a long time.** A chapter opening inside a pataphorical field
carries `\CodexPataphorBegin{seg}{run}` as the paragraph's **first inline** — the Div handler
runs before `Blocks`, because pandoc walks blocks before block *lists*. The old code required
`inl[1].t == "Str"` and bailed silently.

That single condition removed the capital from **25 of 45 chapters in Vol II and 7 of 33 in
Vol I** — the inconsistency Luis reported, and the reason it looked worst in Part V, the most
pataphor-dense part. Nothing in the symptom pointed at the rails.

`codex_lettrine_apply` now walks past leading raw markers to the first real letter, handling
three shapes:

| head inline | meaning | cap |
|---|---|---|
| `Str` | plain prose | normal |
| `RawInline "\CodexPataphorBegin{..}{..}"` | rail marker precedes prose | skip it, letter what follows |
| `RawInline "\CodexSignal{"` then `Str` | a Span, already lowered to three inlines | letter inside the macro → inherits colour |

The Span case is subtle: by the time `Blocks` runs, `[text]{.codex-signal}` is **not** a Span —
the inline pass already emitted an opening `RawInline`, the content, and a closing `"}"`. So the
letter lives at `inl[2]`.

Fail-open throughout: anything that is not an ASCII letter keeps the plain opening.

## Verification

**Coverage** — run the filter over the edition-resolved source and check every
`\OFSetRunningTagline` is followed by a `\CodexLettrine` before the next one:

```
78 chapter openers -> 77 capitals, 1 deliberately bare (Now / Later / Snap, verse)
```

**Geometry** — template-text assertions cannot catch an expl3/kern error. **Smoke-compile**
sample openers (plain, span-opened, quote-opened, verse) through pandoc → lualatex before
trusting a change.

**Never splice this template by computed string offsets.** A 2026-08-03 edit replaced a region
between two anchors that turned out to be **741 lines apart**, deleting `\CodexOpenerEpigraph`,
`\CodexHeartword` and the layered attribution grammar. Caught by the compile and 7 failing
tests, restored with `git checkout HEAD --`. Match on exact content instead.
