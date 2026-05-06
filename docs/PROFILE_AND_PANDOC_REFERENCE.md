# Optical Foundry — Profile and Pandoc Reference Wiring

## Ownership boundary (2026-05-06)

As of commit `32b1358`, Optical Foundry owns editable copies of all
40_latex profile assets in `profiles/40_latex_import/`:

```
profiles/40_latex_import/
├── defaults/    ← 21 YAML defaults (editable copies)
├── templates/   ← 12 .tex templates (editable copies)
└── styles/texmf/tex/latex/
    ├── generic/  ← genericreport.sty, labelsheet.sty, elianpacket.sty
    ├── resume/   ← resume.sty, resumecommon.sty, cv.sty
    └── yugen/    ← yugencommon.sty, yugenrisk.sty, etc.
```

**Resolution order**: PandocRenderer and profile checker prefer local imports
(`profiles/40_latex_import/`) first. If a local copy doesn't exist, they fall
back to `40_latex/` as a read-only reference. All 20 profiles currently resolve
their defaults and templates from local import.

**Editing policy**: Files in `profiles/40_latex_import/` are editable Optical
Foundry copies. The original `40_latex/` tree remains untouched and serves as
the canonical reference. Future profile modifications should happen in the
local import, not in `40_latex/`.

**TEXMFHOME**: The pandoc renderer points `TEXMFHOME` to
`profiles/40_latex_import/styles/texmf` when available, falling back to
`40_latex/styles/texmf`.

---

## Original reference wiring

How the greenfield `42_optical_foundry_greenfield` pipeline references `40_latex`
as a read-only template/style/defaults source.

## Architecture

```
42_optical_foundry_greenfield (greenfield)
  │
  ├── renderers/pandoc_renderer.py       ← PandocRenderDispatch
  │     │
  │     ├── reads templates from:        40_latex/templates/*.tex
  │     ├── reads defaults from:         40_latex/defaults/*.yaml
  │     ├── sets TEXMFHOME to:          40_latex/styles/texmf
  │     └── shells out to:              pandoc + xelatex
  │
  ├── engine/manifest_compiler.py        ← Manifest compilers
  │     └── produces ProjectionPlans consumed by PandocRenderDispatch
  │
  └── cli/__init__.py                    ← CLI entry point
        └── wires manifest registry → compiler → renderer
```

## Profile ID → template mapping

The `PandocRenderer._infer_template()` method maps profile IDs to template
filenames. Templates live in `40_latex/templates/`. This is a read-only
reference — no template is modified.

| Profile ID | Template file | Defaults file |
|---|---|---|
| `generic-report` | `generic_report.tex` | `generic_report.yaml` |
| `risk` | `risk.tex` | `risk.yaml` |
| `cam` | `cam.tex` | `cam.yaml` |
| `tech` | `tech.tex` | `tech.yaml` |
| `creative` | `creative.tex` | `creative.yaml` |
| `mythic` | `mythic.tex` | `mythic.yaml` |
| `mythic-letter` | `mythic_letter.tex` | `mythic_letter.yaml` |
| `letter` | `letter.tex` | `letter.yaml` |
| `resume` | `resume.tex` | `resume.yaml` |
| `prometheus-packet` | `prometheus_packet.tex` | `prometheus_packet.yaml` |
| `convergence` | `convergence.tex` | `convergence.yaml` |
| `keeper` | `keeper.tex` | `keeper.yaml` |
| `labels-avery-5164` | `labels_avery_5164.tex` | `labels_avery_5164.yaml` |
| `labels-avery-15264` | `labels_avery_5164.tex` | `labels_avery_5164.yaml` |
| `sticker-sheet` | `sticker_sheet.tex` | `sticker_sheet.yaml` |

## Style resolution

The Pandoc renderer sets `TEXMFHOME` to `40_latex/styles/texmf` before
invoking xelatex. This lets LaTeX find style packages (`.sty` files) in the
standard TEXMF tree:

```
40_latex/styles/texmf/tex/latex/
  ├── generic/genericreport.sty
  ├── yugen/yugencommon.sty
  ├── yugen/yugenrisk.sty
  ├── yugen/yugencam.sty
  ├── yugen/yugentechnology.sty
  ├── yugen/yugencreative.sty
  ├── yugen/yugenconvergence.sty
  ├── yugen/yugenmythic.sty
  └── resume/resume.sty, resumecommon.sty, cv.sty
```

## How to add a new profile reference

1. Ensure the profile has a template in `40_latex/templates/`.
2. Ensure the profile has a defaults YAML in `40_latex/defaults/`.
3. Add the mapping to `PandocRenderer._infer_template()`.
4. Add a test fixture in `fixtures/sources/` and/or `fixtures/manifests/`.
5. Run `python -m cli doc <fixture> --profile <new-profile>` to validate.

No `40_latex` files are modified. This is a read-only reference architecture.

## Known gaps

Some profiles may have defaults files but no corresponding template (e.g.,
`resume_base`, `resume_cv`). These are recorded in the Optical Foundry packet's
gap report. The greenfield can still render through them if `pandoc` defaults
alone are sufficient; otherwise the profile needs a template.

The source `40_latex` `mythic-letter-johannah` template has a known
`\tightlist` gap documented in the packet. Optical Foundry's **local imported
copy** now carries bundle compatibility support (`\tightlist`, longtable/
booktabs/array, and a `$if(toc)$`-guarded TOC slot) without mutating source
`40_latex`.

## Profile Capability Checker

```bash
# List all profiles with bundle compatibility status
python -m cli profiles

# Check a single profile in detail
python -m cli profiles --profile mythic-letter-johannah

# JSON report for automation
python -m cli profiles --json
```

Implemented in `engine/profile_checker.py`. Reports for each profile:
- `defaults_found` — resolved path to defaults YAML (40_latex or greenfield)
- `template_found` — resolved path to template .tex (40_latex)
- `supports_toc` — template has `$if(toc)$` guard (pandoc `--toc` engages it)
- `has_tightlist` — template defines `\tightlist`
- `has_longtable` — template supports longtable
- `bundle_compatibility` — ok / partial / incompatible with reasons

### Bundle Compatibility Summary (20 profiles)

| Status | Count | Profiles |
|--------|-------|----------|
| ✅ ok | 13 | generic-report, risk, tech, creative, cam, mythic, letter, mythic-letter, mythic-letter-johannah, convergence, keeper, yugen-brand, yugen-brand-elevated |
| ⚠️ partial | 2 | prometheus-packet, resume |
| ❌ incompatible | 5 | elian-packet, elian-poster, labels-avery-5164, labels-avery-15264, sticker-sheet |

### Known Template Mapping Corrections

Some profile IDs still resolve through compatibility corrections because their
historic names don't match filenames on disk. `letter` and `mythic-letter` now
map directly to `personal_letter.tex` in PandocRenderer and the profile checker:

| Profile | Mapped → | Actual template |
|---------|----------|-----------------|
| risk | risk.tex | base.tex |
| tech | tech.tex | base.tex |
| creative | creative.tex | base.tex |
| prometheus-packet | prometheus_packet.tex | generic_report.tex |
| yugen-brand | yugen_brand.tex | generic_report.tex |
| yugen-brand-elevated | yugen_brand_elevated.tex | generic_report.tex |

Remaining corrections are embedded in the profile checker's `TEMPLATE_CORRECTIONS`
dict. Aligning additional renderer mappings remains a local-import-only
implementation pass if/when those profiles become active render targets.

## Label / sticker placeholder E2E posture

`label-run` and `sticker-sheet` now have explicit synthetic placeholder E2E
behavior in Optical Foundry:
- both render through normal `foundry manifest` with local imported assets only
- evidence marks `boundary.layout_mode = content_driven_placeholder`
- evidence marks `boundary.grid_validated = false`
- warnings explain that physical Avery/sticker grid placement is still
  content-driven and not validated by the current compiler

This makes the current limitation honest and testable without pretending a full
grid engine exists.
