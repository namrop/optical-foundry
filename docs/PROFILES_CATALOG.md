# Optical Foundry — Profiles Catalog (what each profile is for)

Purpose-oriented companion to `PROFILE_AND_PANDOC_REFERENCE.md` (which covers the *wiring*:
ID→template mapping, style resolution, the capability checker, parindent). This doc answers
the operator/agent question: **"I have a document — which profile do I render it with, and
what will it look like?"**

**Source of truth:** the `PROFILE_SPECS` map in `engine/profile_resolver.py`. If this catalog
and the resolver disagree, the resolver wins — update this doc. `python -m cli profiles`
lists every profile with live bundle-compatibility status.

**Where profiles live (SIL-32, 2026-10-21; rulings `01a0f99a-b2db`, `01a14634-bff0`).** The engine
keeps only the base and the demo profiles Luis chose: `document-spine`, `generic-report`, `letter`,
`short-story`, `labels-avery-5164`, `labels-avery-15264`, `sticker-sheet`. (`codex0-a5` left with
SIL-31, 2026-10-21.) Every other profile below is a profile package in the `optical-foundry-profiles`
repository, under the same id, found through `OF_PROFILE_PATH` or
`~/.config/optical-foundry/profile_repos` (`engine/profile_package.py`). A host without that pointer
renders only the engine's profiles. The Yugen, Oasis, Keeper and life packages share the
`yugen-brand` package's `yugenbase.yaml`, `yugencommon.sty` and logo by relative path.

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
| **`client_report`** | `client_report.tex` | **Client security reports** (internal/client/public). Frontmatter-driven classification marking, cover metadata, footers, PDF metadata, and figure caption/numbering — see the [frontmatter contract guide](guides/client-report-frontmatter-contract.md). Template/defaults/sty are **gitignored client brand assets** (on-disk only). Served over the remote MCP (`render_report`, inline Markdown). |
| `yugen_tech` (`tech`) | `base.tex` | Yugen-branded **technical** documents. |
| `yugen_risk` (`risk`) | `base.tex` | Yugen **risk / security** documents. |
| `yugen_creative` (`creative`) | `base.tex` | Yugen **creative** documents. |
| `yugen_civic` (`civic`, `yugen-civic`) | `base.tex` | Yugen **civic** documents. |
| `yugen-brand` / `yugen-brand-elevated` | `generic_report.tex` | Yugen brand collateral (elevated = richer treatment). |
| `cam` | `cam.tex` | CAM (civic-abundance) documents. |
| `mythic` | `mythic.tex` | mythic-register documents (non-letter). |
| **`codex0`** | `codex0.tex` | **Codex 0 (the book), letter-size.** Inherits the Johannah-letter defaults then overrides with `codex0.yaml`. This is the profile for Codex 0 v5 renders (frontmatter fragments, part dividers, whole-book bundles). |
| `codex0-a5` (`codex0_a5`) | `codex0_a5.tex` | the older Codex 0 variant in **A5** trim; carries the Codex 0 image initial `assets/dropcaps/codex0/I.png`. |
| `convergence` | `convergence.tex` | psychohistory convergence documents. |
| `keeper` | `keeper.tex` | Keeper-Order documents. |
| `life` | `base.tex` | life & logistics documents. |
| `prometheus-packet` | `generic_report.tex` | Prometheus packet (⚠ shares the generic template — partial). |
| **`short-story`** (`short_story`) | `short_story.tex` + `filters/short_story.lua` | **one piece of short fiction**, set like a story in a small book. Codex 0's half-letter trim, Iowan Old Style 10.5/14.2 with old-style figures, book paragraphs (first-line indents, no space between), the title block on page one in the Iowan titling capitals rather than a separate title page, a letterspaced small-caps running head from page two, a centred folio. Source grammar: a Markdown horizontal rule (`***`) is a scene break (centred `* * *`); the first paragraph and the first after a break start flush; the first paragraph opens with a two-line `lettrine` drop cap (an opening quote is carried as `ante`) unless frontmatter sets `ss_dropcap: false`. Frontmatter: `title`, optional `subtitle`, `author` (renders "by …"), `running_title`. Sample: `fixtures/sources/short_story_sample.md`. Opened 2026-09-29 for the horror anthology seeds. |

### `periodical` — issues of a recurring printed paper

| Profile | Template | Use it for |
|---|---|---|
| **`household-paper`** (`household_paper`, `household-newspaper`) | `household_paper.tex` + `filters/household_paper.lua` | **the household newspaper** (descriptive handle; the masthead is unminted and renders as a labelled slot). Letter pages, one grid for both bindings (head-bound pad now, folded 11 × 17 later), three columns at 10.5/12.5 with two at 11/13.5 on the feature and private classes, greyscale-only output (xcolor `gray`, no hyperref → DeviceGray, prints in black-ink-only mode). Five page classes lowered from fenced divs: `front`, `section`, `feature`, `flex`. Fonts are vendored (XCharter, Playfair Display, Chivo, Old Standard). Per-issue variables (`hp_issue_line`, `hp_issue_date_long`, `hp_issue_id`, …) are raw LaTeX: plain text, no `%`. Sample: `fixtures/sources/household_paper_sample_issue.md`. |

> ⚠ `household-paper` renders one issue, not a bundle (`partial`): tables inside columns lower to `tabularx`, not longtable, and there is no TOC.

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
