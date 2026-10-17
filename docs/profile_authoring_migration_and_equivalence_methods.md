---
uid: 01a12c49-a666-7088-a66e-3cd0796e8154
kind: note
note_role: learning
thinking_mode: reference
validation_profile: standard
status: active
created: '2026-10-11T18:46:26+00:00'
updated: 2026-10-11T20:18:11+00:00
beam_home: docs
title: Optical Foundry methods — adding a profile, proving "no output change", and moving a profile into a package
  (2026-09-29 to 2026-10-03)
summary: Adding a Foundry profile touches a fixed set of files and has three typesetting traps; a refactor that
  should not change output can be proved in minutes by diffing the LaTeX pandoc would compile, with the whole-book
  comparison kept where Luis's cadence ruling puts it; and a profile moves into a package by byte-identical copy,
  probe, then delete.
author:
  name: Lux
  model: claude-opus-5-5
  provider: custom:primary
  harness: Hermes Agent over ACP, in T3 Code (implementation sub-agent)
  voyage: unknown
  at: '2026-10-11T18:46:26+00:00'
last_touched: {"name": "Lux", "harness": "hermes-agent", "model": "gpt-6.1-sol", "provider": "openai-codex", "voyage": "t3:thread:mcp:1fbe173e-b733-43f7-ab55-0025c7e7eb58", "at": "2026-10-11T20:18:11+00:00"}
principal: luis
trigger:
  initiative: luis_direct
  ratification: ratified
  summary: 'Luis approved promotion of the reviewed residuals in T3 mcp:1fbe173e-b733-43f7-ab55-0025c7e7eb58: agreed.
    lets do the folds and new notes please. then we can archive the ledgers and turn off the prompts instructing
    that we make new beam photons. Historical source instructions are not re-ratified.'
---

# Optical Foundry methods — adding a profile, proving "no output change", and moving a profile into a package (2026-09-29 to 2026-10-03)

## Pith

Adding a Foundry profile touches a fixed set of files and has three typesetting traps; a refactor that should not change output can be proved in minutes by diffing the LaTeX pandoc would compile, with the whole-book comparison kept where Luis's cadence ruling puts it; and a profile moves into a package by byte-identical copy, probe, then delete.

## Abstract

Keeps five photons from the 2026-09-29 short-story profile work and the 2026-10-01 to 2026-10-03 Codex 0 refactor. Adding a profile needs defaults, template and optional filter files, resolver and checker entries, a catalog row, a synthetic fixture and a real render test, and runs into three traps: Lua filters see only doc.meta, +smart turns a quoted opening into a Quoted element, and Iowan Titling has capitals only. A structural refactor's per-step check is a capture of the LaTeX pandoc would compile for a fixed case set, diffed after normalising run-local roots; Luis's 2026-10-01 ruling 01a0f8ba-4937 keeps the whole-book contact-sheet comparison for the end of a refactor run and any step he names. Moving a profile into a package uses ${.} paths in its defaults, a byte-identical copy and pixel probe before deletion, and package-aware tests and checker. The commit and push order describes how commissioned Foundry work was landed on those dates; it is not a default to push.

## Context

Promoted from the approved beam-ledger preservation review on 2026-10-11. This note keeps source-time scope, origin and evidence status; it is not independent ratification of model-authored rules.

## Learning

Sources, all in the 23_metacognition ledger, medium confidence: `P-2026-09-29-014`, `P-2026-09-29-021` and `P-2026-10-03-007` are model-origin (Lux). `P-2026-10-01-013` and `P-2026-10-01-015` are recorded as mixed: the cadence they cite is Luis's ruling, and the capture-and-diff recipe is Lux's.

### Adding a profile

Sources: `P-2026-09-29-014` and `P-2026-09-29-021`, both Hermes session `20260929_105128_3398ba72`. Two captures of the work that added the `short-story` profile (alias `short_story`). All 13 new tests passed; the Foundry commit was `54a9546` and the parent pointer `ebfa7e57e`. At the time the render-pipeline skill was over its 100k-character limit and could not be patched, and it did not cover this procedure on Sol.

Work in the canon submodule `42_optical_foundry` and run `python3 -m cli ...` after checking `python3 -c "import yaml"`.

#### Files a new profile touches

- `profiles/40_latex_import/defaults/<id>.yaml`: pdf-engine, template, filters.
- `profiles/40_latex_import/templates/<id>.tex`, self-contained: a `$for(header-includes)$` loop, `\providecommand{\tightlist}`, `\providecommand{\pandocbounded}[1]{#1}`, `\setcounter{secnumdepth}{-\maxdimen}`.
- Optionally `filters/<id>.lua`.
- `engine/profile_resolver.py`: the `PROFILE_SPECS` entry and an underscore alias in `ALIASES`.
- `engine/profile_checker.py`: the known-profile set and a classification (`TIGHTLIST_PROFILES` plus `BUNDLE_PARTIAL` or `BUNDLE_OK`, with a classification-reasons entry). Without one, `check_profile` reports no known classification.
- `docs/PROFILES_CATALOG.md`: a row in the right family table.
- `fixtures/sources/<id>_sample.md`: synthetic text, never keeper writing.
- `tests/test_<id>_profile.py`: resolver, alias, checker and font policy; the filter's LaTeX output through `pandoc --lua-filter`; and one real render through `python3 -m cli doc <src> --profile <id> --output <dir>`, checked with `pdfinfo -box` (MediaBox), `pdffonts`, and `pdftotext` for macro leaks.

#### Three typesetting traps

1. **Filters see only `doc.meta`.** Lua filters do not see a defaults file's `variables:`, and a defaults `metadata:` block overrides frontmatter the way `--metadata` does. Put filter defaults in the filter, with a frontmatter switch.
2. **Drop caps under `+smart`.** With `markdown+smart`, a paragraph opening with a straight `"` reaches the filter as a `Quoted` inline, not a `Str`. A `lettrine` filter must handle `Quoted` by taking its first inner `Str`, pass the opening curly quote as `ante=`, and re-insert the closing quote after the inner content. A filter that checks only for `Str` silently skips quoted openings. Pandoc's LaTeX writer spells the closing curly quote as `''` and the apostrophe as `'`, so tests asserting on generated LaTeX must expect those, not U+201D and U+2019.
3. **Iowan Titling is capitals only.** Face 6 of the vendored Iowan Old Style TTC has no lowercase glyphs, and the render's missing-character lint fails on them. Set the title through `\MakeUppercase{...}`.

#### Inherited suite failures

Before blaming a new profile, run the full suite. Prove any failure pre-existing with `git stash push -u`, the failing tests alone at the base, then `git stash pop`. At `c6fa643` four codex0 tests failed the same way with and without the change, and were reported as inherited.

#### How the 2026-09-29 work was landed

That commission was committed and pushed in this order: a submodule commit (`git add` the new files, `commit --only`); a push to the remote whose `main` tracked HEAD (check `git rev-list --count <remote>/main..HEAD`; on 2026-09-29 deneb matched and origin lagged); then the parent pointer with `git commit --only -- 42_optical_foundry`. The order matters when a commission includes landing the change: the parent should not point at a submodule commit no remote has. It is a record of that commission's sequence, not a default to push.

### Proving a refactor changes no output

Sources: `P-2026-10-01-013` (Hermes session `deb7a987-2248-4c7a-a617-a78d4cf2ced5`) and `P-2026-10-01-015` (same session). Two captures of one method.

#### Luis's cadence (already ruled)

`42_optical_foundry/RULINGS.md` holds ruling `01a0f8ba-4937` (2026-10-01, T3 Code thread, recorded also in memory fact 1045): do not run whole-book contact-sheet comparisons between refactor steps; one at the end of a refactor run proves the Foundry still outputs what it did, plus any step he singles out. He named the template contract as such a step. That comparison is `CODEX0_REGRESSION=1 build/run_full_build.sh <run>` (`FOUNDRY=<worktree>` renders from a branch), then `build/compare_runs.py <baseline-run> <candidate-run>`. The ruling is overlap here; `P-2026-10-01-015` was marked promoted on 2026-10-05 for it (proposal A-36, keeper ruling `01a10d69-9936-7f41-83ad-188f4ac3a31a`).

#### The per-step check: captured LaTeX

For structural refactors (preamble routing, the template contract, moves in source preparation), prove equivalence in minutes instead of a whole-book build of about ten minutes:

1. Monkeypatch `subprocess.run` in `renderers.pandoc_renderer` so each pandoc call has its `--pdf-engine` options stripped and writes LaTeX (`-t latex`, `-o` redirected to a `.tex` file) instead of compiling.
2. Run a fixed case list against both the old checkout and the worktree: several profiles on a glyph, strikeout, emoji and CJK probe source; a source with header-includes; draft renders; the three Codex 0 volume manifests from the latest regression run, with `bake_images`; and one keeper-capture volume through `engine.volumes.split_manifest` with `body_folio_start` set.
3. Diff baseline against candidate, ignoring blank lines, after normalising run-local paths. Resolve both output directories first, then replace each checkout root with a token. Do not substitute substrings such as "base", or words like "baseline" and "candidate" get mangled.
4. Identical captured LaTeX for every case is the per-step check.

Run the base and candidate captures, and the full pytest suite, in the background; each takes several minutes and the suite exceeds the 600 s foreground limit. Compare suite results against the known-failure set. In the Codex 0 refactor the captured LaTeX was identical before and after for 15 cases, including the three Codex 0 volumes and keeper-capture Volume II, as the refactor voyage records.

### Moving a profile out of the engine into a package

Source: `P-2026-10-03-007`, Hermes session `deb7a987-2248-4c7a-a617-a78d4cf2ced5`. Worked for Codex 0 (step G2, 2026-10-03; Foundry `8a0cab0`, profiles `c8f4ec4`), with whole-book output identical.

1. **The package's `profile.yaml`** declares family, `base_defaults` (the engine defaults it builds on, replacing the extended profile's stack), defaults, template, `tex: [tex]`, markers and editions. Directories under `tex` go first on `TEXINPUTS` and `LUAINPUTS`. LuaTeX `require()` searches `LUAINPUTS`, not `TEXINPUTS`, so set both; the render-pipeline skill's LuaTeX reference already holds that point.
2. **Package-relative paths.** Inside the package's pandoc defaults file, reference package files as `${.}/../filters/x.lua`; pandoc expands `${.}` to the defaults file's directory. The renderer's declared-filter scan must expand `${.}` too.
3. **Move in order.** Copy the files byte-identical, render a small probe before and after deleting the engine copies and compare pixels, then `git rm` the engine copies and drop the `PROFILE_SPECS` entry.
4. **Tests and checker.** Tests stay in the engine but locate the package through `resolve_profile(id).boundary['profile_package']` (`tests/codex0_package.py`), skipping where no profile-repo pointer exists. `profile_checker` must accept `defaults_source` `local+package` and `template_source` `package`.
5. **Finish** with the full Codex 0 build and `compare_runs.py` against the previous run, which is the end-of-run comparison the cadence ruling calls for.

### Source register

The following are dated source captures, not newly ratified instructions. The synthesis above states the retained residuals; source-time measurements, commissioned actions, assistant judgments and unresolved claims retain their original scope. Full metadata, feedback and lifecycle history remain in the archival source ledger.

#### Adding a new Optical Foundry profile on Sol (short-story, 2026-09-29)

Source: `23_metacognition/photon_ledgers/provisional_photon_ledger_2026-05-19.jsonl#P-2026-09-29-014`. Captured: `2026-09-29T15:18:59-04:00`. Origin: `model_origin`; originator: `Lux`. Record SHA-256: `c4683316a7a852b60554a861565286d1f5f0d02138b27f50e43edd24db783b77`.

Source text:

> Verified procedure for adding a profile, which the skill (now over its 100k-char limit, so it could not be patched) does not cover for Sol. Work in the canon submodule 42_optical_foundry and run `python3 -m cli ...` after checking `python3 -c "import yaml"`. Files: profiles/40_latex_import/defaults/<id>.yaml (pdf-engine, template, filters), a self-contained templates/<id>.tex ($for(header-includes)$ loop, \providecommand{\tightlist}, \providecommand{\pandocbounded}[1]{#1}, \setcounter{secnumdepth}{-\maxdimen}), optional filters/<id>.lua; PROFILE_SPECS + ALIASES entries in engine/profile_resolver.py; a classification in engine/profile_checker.py (TIGHTLIST_PROFILES plus BUNDLE_PARTIAL/BUNDLE_OK, else check_profile reports no known classification); a row in docs/PROFILES_CATALOG.md; a synthetic fixture in fixtures/sources/; tests for resolver/alias/checker/font policy, pandoc+filter LaTeX output, and one real CLI render measured with pdfinfo -box, pdftotext and pdffonts. Pitfalls: Lua filters see only doc.meta, not defaults variables:, and a defaults metadata: block overrides frontmatter like --metadata, so filter defaults belong in the filter with a frontmatter switch; under +smart a paragraph opening with a straight double quote is a Quoted element, not a Str, and pandoc writes the closing curly quote as ''; the render's missing-character lint fails on glyphs absent from a face (Iowan face 6, Titling, is capitals-only, so uppercase what is set in it). Before committing run the full suite; prove any failures pre-existing with `git stash push -u`, the failing tests, `git stash pop`. Commit order: submodule commit, push to the remote whose main tracks HEAD (check `git rev-list --count <remote>/main..HEAD`; on 2026-09-29 deneb matched, origin lagged), then the parent pointer with `git commit --only -- 42_optical_foundry`.

Source compression:

> New OF profile on Sol: defaults+template+filter, resolver+checker+catalog+fixture+tests with a real render; filters read doc.meta only; +smart quotes are Quoted; caps-only titling trips the glyph lint; baseline failures via stash; push to the remote tracking main before the parent pointer.

Original source references:

```json
[
  {
    "kind": "transcript",
    "relation": "primary_source",
    "note": "Hermes session 20260929_105128_3398ba72"
  }
]
```

#### Adding an Optical Foundry profile: file set and three typesetting traps (short-story, 2026-09-29)

Source: `23_metacognition/photon_ledgers/provisional_photon_ledger_2026-05-19.jsonl#P-2026-09-29-021`. Captured: `2026-09-29T16:55:42-04:00`. Origin: `model_origin`; originator: `Lux`. Record SHA-256: `8318682d8650cd9ca8db60d4772de1d43d25f82fd67895554060b411c73c4e44`.

Source text:

> This is the set of changes that added the `short-story` profile. It worked and all 13 new tests passed (OF commit 54a9546, parent pointer ebfa7e57e).
>
> **Files a new profile touches**
> - `profiles/40_latex_import/defaults/<name>.yaml`
> - `profiles/40_latex_import/templates/<name>.tex`
> - optionally `filters/<name>.lua`
> - `engine/profile_resolver.py`: the profile entry, plus an underscore alias
> - `engine/profile_checker.py`: the known-profile set, plus a classification-reasons entry
> - `docs/PROFILES_CATALOG.md`: a row in the right family table
> - `fixtures/sources/<name>_sample.md`: synthetic text, never keeper writing
> - `tests/test_<name>_profile.py`: resolution, the filter lowering through `pandoc --lua-filter`, and one real render through `python3 -m cli doc <src> --profile <name> --output <dir>`, checked with pdfinfo MediaBox, pdffonts and pdftotext for macro leaks
>
> Commit inside the submodule with `git add` for the new files and `commit --only`. Push to deneb, then commit the parent-repo pointer with `--only -- 42_optical_foundry`.
>
> **Typesetting traps**
> 1. **Iowan Titling is capitals only.** The Iowan Old Style Titling cut (face 6 of the vendored TTC) has no lowercase glyphs. Set the title through `\MakeUppercase{...}`. Otherwise the lowercase letters are missing from the render.
> 2. **Drop caps under +smart.** With `markdown+smart`, a paragraph that opens with `"` arrives in the Lua filter as a `Quoted` inline, not a `Str`. A `lettrine` drop-cap filter must:
>    - handle `Quoted`, taking its first inner `Str`;
>    - pass the opening curly quote as `ante=`;
>    - re-insert the closing quote after the inner content.
>    A filter that only checks for `Str` silently skips quoted openings.
> 3. **Pandoc's quote spelling.** Pandoc's LaTeX writer spells the closing curly quote as `''` and the apostrophe as `'`. Tests that assert on generated LaTeX must expect those, not U+201D and U+2019.
>
> **Before blaming a new profile for suite failures**
> Stash your changes (`git stash push -u`), rerun only the failing tests at the base commit, then `git stash pop`. At c6fa643, four codex0 tests failed the same way with and without the change. Report inherited failures that way instead of chasing them.

Source compression:

> New OF profile = defaults+template+filter+resolver alias+checker+catalog+fixture+render test; Iowan Titling caps-only; lettrine must handle Quoted under +smart; pandoc LaTeX quotes are ''/'.

Original source references:

```json
[
  {
    "kind": "transcript",
    "relation": "primary_source",
    "note": "Hermes session 20260929_105128_3398ba72"
  }
]
```

#### Cheap no-change proof for Foundry refactors: diff the LaTeX pandoc would compile

Source: `23_metacognition/photon_ledgers/provisional_photon_ledger_2026-05-19.jsonl#P-2026-10-01-013`. Captured: `2026-10-01T17:10:13-04:00`. Origin: `mixed`; originator: `Luis and Lux`. Record SHA-256: `4bec792e0849162658891922962941dac3b92f02249b3b0027b96d1e7b68f238`.

Source text:

> For refactors that should not change output, prove it in minutes instead of a ~10-minute whole-book build: monkeypatch subprocess.run in renderers.pandoc_renderer so each pandoc call has its --pdf-engine options stripped and -o redirected to a .tex file, run a fixed case list (several profiles on a glyph/strikeout/CJK probe source, a source with header-includes, draft renders, the Codex 0 volume manifests from the latest regression run with bake_images, one keeper-capture volume via engine.volumes.split_manifest with body_folio_start set) against both the old checkout and the worktree, then diff with run-local paths normalised (resolve the output dirs before replacing them, or words like "baseline"/"candidate" get mangled) and blank lines ignored. Identical captured LaTeX for all cases is the per-step check; Luis's ruling 01a0f8ba-4937 keeps the full Codex 0 contact-sheet comparison (CODEX0_REGRESSION=1 build/run_full_build.sh + build/compare_runs.py) for the end of a refactor run plus any step he singles out. Run base and candidate captures in background (each takes several minutes; foreground calls time out).

Source compression:

> Cheap no-change proof for Foundry refactors: diff the LaTeX pandoc would compile

Original source references:

```json
[
  {
    "kind": "transcript",
    "relation": "primary_source",
    "note": "Hermes session deb7a987-2248-4c7a-a617-a78d4cf2ced5"
  }
]
```

#### Foundry refactors: prove "no output change" by diffing captured pandoc LaTeX, whole-book compare only where the keeper asks

Source: `23_metacognition/photon_ledgers/provisional_photon_ledger_2026-05-19.jsonl#P-2026-10-01-015`. Captured: `2026-10-01T17:17:46-04:00`. Origin: `mixed`; originator: `Luis and Lux`. Record SHA-256: `df54f65b25290d658f00c2881c5522d8e8b0902dd3753a132db410ebbd55f41c`.

Source text:

> For structural Optical Foundry refactors (preamble routing, template contract, source preparation moves), a cheap equivalence proof is: monkeypatch the renderer's subprocess so pandoc writes LaTeX (-t latex) instead of compiling, capture the .tex for a fixed case set (several profiles on a glyph/strikeout/emoji probe, draft renders, the three Codex 0 volume manifests incl. bake_images, one keeper-capture volume via engine.volumes.split_manifest), and diff baseline vs candidate after normalising run-local paths (resolve both dirs; replace checkout roots with a token, NOT substring 'base' etc.). Identical LaTeX across all cases = no output change, in seconds, without the ~10 min whole-book build. Luis's 2026-10-01 rule (ruling 01a0f8ba): do not run whole-book contact-sheet comparisons between refactor steps; one at the end proves the Foundry still outputs what it did — except where he names a step as worth the check (he named the template contract). Run the full pytest suite in the background (>600s foreground limit) and compare against the known-failure set.

Source compression:

> Foundry refactors: prove "no output change" by diffing captured pandoc LaTeX, whole-book compare only where the keeper asks

Original source references:

```json
[
  {
    "kind": "transcript",
    "relation": "primary_source",
    "note": "Hermes session deb7a987-2248-4c7a-a617-a78d4cf2ced5"
  },
  {
    "kind": "markdown_note",
    "relation": "promoted_artifact",
    "path": "42_optical_foundry/RULINGS.md",
    "note": "Marked promoted 2026-10-05: the content was already in this note (beam-photon review proposal A-36; keeper ruling 01a10d69-9936-7f41-83ad-188f4ac3a31a)."
  }
]
```

#### Moving a whole Optical Foundry profile out of the engine into a profile package

Source: `23_metacognition/photon_ledgers/provisional_photon_ledger_2026-05-19.jsonl#P-2026-10-03-007`. Captured: `2026-10-03T05:01:35-04:00`. Origin: `model_origin`; originator: `Lux`. Record SHA-256: `f71c365b6b0a4f5fe6edfc0a3338ce7f61506edcd694d63cad02216130ba33be`.

Source text:

> Worked for Codex 0 (G2, 2026-10-03; Foundry 8a0cab0, profiles c8f4ec4), whole-book output identical. Steps: (1) The package profile.yaml declares family, base_defaults (engine defaults it builds on, replacing the extended profile's stack), defaults, template, tex: [tex] (directories put first on TEXINPUTS and LUAINPUTS; LuaTeX require() does not follow TEXINPUTS, so LUAINPUTS must be set separately), markers and editions. (2) Inside the package's pandoc defaults file, reference package files as ${.}/../filters/x.lua (pandoc expands ${.} to the defaults file's directory); the renderer's declared-filter scan must expand ${.} too. (3) Copy files byte-identical, render a small probe before and after deleting the engine copies and compare pixels, then git rm the engine copies and drop the PROFILE_SPECS entry. (4) Tests stay in the engine but locate the package via resolve_profile(id).boundary['profile_package'] (tests/codex0_package.py), skipping where no profile-repo pointer exists; profile_checker must accept defaults_source 'local+package' and template_source 'package'. (5) Finish with the full Codex 0 build and compare_runs.py against the previous run.

Source compression:

> Moving a whole Optical Foundry profile out of the engine into a profile package

Original source references:

```json
[
  {
    "kind": "transcript",
    "relation": "primary_source",
    "note": "Hermes session deb7a987-2248-4c7a-a617-a78d4cf2ced5"
  }
]
```
