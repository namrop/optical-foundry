# Optical Foundry — Profiles Catalog (what each profile is for)

Purpose-oriented companion to `PROFILE_AND_PANDOC_REFERENCE.md` (which covers the *wiring*:
ID→template mapping, style resolution, the capability checker, parindent). This doc answers
the operator/agent question: **"I have a document — which profile do I render it with, and
what will it look like?"**

**Source of truth:** the `PROFILE_SPECS` map in `engine/profile_resolver.py`. If this catalog
and the resolver disagree, the resolver wins — update this doc. `python -m cli profiles`
lists every profile with live bundle-compatibility status.

---

## Mental model: a profile is a stack, not a single file

A profile resolves to three things:

1. a **template** (`profiles/40_latex_import/templates/*.tex`) — the LaTeX skeleton (page
   geometry, header/footer, color macros, title/TOC handling);
2. a **defaults stack** (`profiles/40_latex_import/defaults/*.yaml`) — pandoc metadata layered
   **in order, later overriding earlier** (e.g. `document_spine.yaml` → `yugenbase.yaml` →
   `codex0.yaml`);
3. **asset roots + font policy + a boundary** (where images resolve, which fonts are allowed).

So "the codex0 look" is `codex0.tex` + `[document_spine, personal_letter,
mythic_letter_johannah, codex0].yaml` stacked — it literally inherits the Johannah-letter
aesthetic and then overrides it. Aliases (e.g. `tech`→`yugen_tech`, `codex-0`→`codex0`) are in
`profile_resolver.ALIASES`.

## Render invocations

```bash
# single markdown document
python -m cli doc --profile <profile-id> --output <out-dir> <file.md>

# from a bundle/document manifest (books, multi-source)
python -m cli manifest <bundle.codex-bundle.yaml>

# inspect a profile's resolution / compatibility
python -m cli profiles --profile <profile-id>
```

---

## Families and the catalog

### `stationery_art` — letters and personal correspondence art

Warm, single-column, header/footer script, ornamental rules, inline vignettes. **No TOC.**

| Profile | Template | Use it for |
|---|---|---|
| `letter` | `personal_letter.tex` | a plain personal letter (generic stationery). |
| `mythic-letter` | `personal_letter.tex` | a personal letter in the mythic register. |
| **`mythic-letter-johannah`** | `mythic_letter_johannah.tex` | **a personal letter series** (numbered letters, #NN). Forest-green body (`0E5035`), burgundy accents (`800020`/template `8B2942`), gold rules/ornaments, calligraphic header/footer (Conceived/Penned/desk-of), inline `of-image` ink-wash vignettes. This is the profile for that letter series. |

### `document_spine` — structured documents, reports, and the book

Multi-section documents with TOC support, running heads, the shared `base.tex` spine (or a
per-profile template). This is the biggest family.

| Profile | Template | Use it for |
|---|---|---|
| `document-spine` | `base.tex` | the bare document skeleton (rarely used directly). |
| `generic-report` | `generic_report.tex` | plain, unbranded reports. |
| `yugen_tech` (`tech`) | `base.tex` | Yugen-branded **technical** documents. |
| `yugen_risk` (`risk`) | `base.tex` | Yugen **risk / security** documents. |
| `yugen_creative` (`creative`) | `base.tex` | Yugen **creative** documents. |
| `yugen_civic` (`civic`, `yugen-civic`) | `base.tex` | Yugen **civic** documents. |
| `yugen-brand` / `yugen-brand-elevated` | `generic_report.tex` | Yugen brand collateral (elevated = richer treatment). |
| `cam` | `cam.tex` | CAM (civic-abundance) documents. |
| `mythic` | `mythic.tex` | mythic-register documents (non-letter). |
| **`codex0`** | `codex0.tex` | **Codex 0 (the book), letter-size.** Inherits the Johannah-letter defaults then overrides with `codex0.yaml`. This is the profile for Codex 0 v5 renders (frontmatter fragments, part dividers, whole-book bundles). |
| `codex0-a5` | `codex0_a5.tex` | Codex 0 in **A5** trim. |
| `convergence` | `convergence.tex` | psychohistory convergence documents. |
| `keeper` | `keeper.tex` | Keeper-Order documents. |
| `life` | `base.tex` | life & logistics documents. |
| `prometheus-packet` | `generic_report.tex` | Prometheus packet (⚠ shares the generic template — partial). |

### `resume` — CVs

| Profile | Template | Use it for |
|---|---|---|
| `resume` | `resume.tex` | resumes / CVs (no TOC; `--toc` has no effect). |

### `campaign_art` — campaign collateral (needs real external art)

| Profile | Template | Use it for |
|---|---|---|
| `elian-packet` | `elian_packet.tex` | Elian campaign packet. |
| `elian-poster` | `elian_poster.tex` | Elian campaign poster. |

> ⚠ Campaign profiles are **bundle-incompatible** for synthetic local renders — they carry
> placeholder assets only; real campaign art is external/content-dependent.

### `physical_sheet_profile` — grids for physical media (not documents)

| Profile | Template | Use it for |
|---|---|---|
| `labels-avery-5164` | `label_sheet.tex` | Avery 5164 label grid. |
| `labels-avery-15264` | `label_sheet.tex` | Avery 15264 label grid. |
| `sticker-sheet` | `label_sheet.tex` | sticker sheets. |

> ⚠ Sheet profiles are **document-incompatible** — they lay out label/sticker grids, not prose
> bundles. Don't render narrative documents with them.

---

## Operational notes & gotchas (learned in practice)

- **Render letters through their profile, not a generic path.** A letter rendered without
  `--profile mythic-letter-johannah` (e.g. a bare `doc` render, or a draft missing its
  `variables:` block) falls back to a generic template whose body is **black**, not the series
  green. Symptom: the body reads darker than the other letters and darker than the green
  vignettes. Fix: render with `--profile mythic-letter-johannah` and give the letter a
  `variables:` block (mirror a delivered letter — opening, signature_name, artifact_series,
  conceived/penned dates, artifact_location, desk_of, linestretch, parskip, body_top_vspace).

- **The `0E`-hex `body_color` float trap.** The Johannah-letter body default is `0E5035`,
  hardcoded in `mythic_letter_johannah.tex` (the `$if(body_color)$…$else$…$endif$` line). **Do
  not** set `body_color: "0E5035"` in a document's `variables:` to "make sure" — the foundry
  re-emits it unquoted, and downstream YAML reads `0E5035` as the float `0e5035` → `0`,
  producing `\definecolor{LetterBody}{HTML}{0}` and a LaTeX crash. Leave `body_color` unset and
  let the template's literal default apply. (Any `0E`/`0e`-prefixed hex that looks like sci-
  notation has the same hazard — quote-and-hope is not enough once it round-trips through the
  metadata layer.)

- **Defaults stack order matters.** To change one value, add it to the *last* defaults file in
  the profile's stack (or override in the document frontmatter), not an earlier one an inner
  layer will re-override.

- **`codex0` is a letter-descended profile.** Its defaults include `personal_letter.yaml` and
  `mythic_letter_johannah.yaml` before `codex0.yaml`, so book-wide overrides that need to beat
  the letter aesthetic must live in `codex0.yaml` (see the note in `defaults/codex0.yaml`).

- **Check compatibility before rendering something unusual:** `python -m cli profiles` flags
  `❌ incompatible` (label/sticker/campaign) and `⚠ partial` (resume: no TOC; prometheus-packet:
  generic template) profiles.

---

## Adding or changing a profile

See `PROFILE_AND_PANDOC_REFERENCE.md` §"How to add or modify a profile". In short: add the
template (`templates/`), the defaults YAML(s) (`defaults/`), and an entry in
`PROFILE_SPECS` (and an `ALIASES` entry if the historic name differs from the id). Then verify
with `python -m cli profiles --profile <id>`.
