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

**Resolution order**: PandocRenderer and profile checker resolve defaults,
templates, styles, and profile assets from the Foundry-owned import tree
(`profiles/40_latex_import/`). There is no active runtime fallback to the
external legacy profile tree.

**Editing policy**: Files in `profiles/40_latex_import/` are editable Optical
Foundry copies. Profile modifications happen in that local import tree.

**TEXMFHOME**: The pandoc renderer points `TEXMFHOME` to
`profiles/40_latex_import/styles/texmf`.

---

## Runtime wiring

Optical Foundry no longer treats the legacy profile tree as a live fallback.
The renderer resolves through this Foundry-owned surface:

```
42_optical_foundry
  │
  ├── renderers/pandoc_renderer.py       ← PandocRenderDispatch
  │     │
  │     ├── reads templates from:        profiles/40_latex_import/templates/*.tex
  │     ├── reads defaults from:         profiles/40_latex_import/defaults/*.yaml
  │     ├── reads assets from:           profiles/40_latex_import/assets/
  │     ├── sets TEXMFHOME to:           profiles/40_latex_import/styles/texmf
  │     └── shells out to:               pandoc + xelatex
  │
  ├── engine/manifest_compiler.py        ← Manifest compilers
  │     └── produces ProjectionPlans consumed by PandocRenderDispatch
  │
  └── cli/__init__.py                    ← CLI entry point
        └── wires manifest registry → compiler → renderer
```

## Profile ID → template mapping

The shared profile resolver maps profile IDs to template/default filenames under
`profiles/40_latex_import/`.

| Profile ID | Template file | Defaults file |
|---|---|---|
| `generic-report` | `generic_report.tex` | `generic_report.yaml` |
| `risk` | `risk.tex` | `risk.yaml` |
| `cam` | `cam.tex` | `cam.yaml` |
| `tech` | `tech.tex` | `tech.yaml` |
| `creative` | `creative.tex` | `creative.yaml` |
| `mythic` | `mythic.tex` | `mythic.yaml` |
| `mythic-letter` | `personal_letter.tex` | `mythic_letter.yaml` |
| `letter` | `personal_letter.tex` | `letter.yaml` |
| `resume` | `resume.tex` | `resume_resume.yaml` |
| `prometheus-packet` | `generic_report.tex` | `prometheus_packet.yaml` |
| `convergence` | `convergence.tex` | `convergence.yaml` |
| `keeper` | `keeper.tex` | `keeper.yaml` |
| `labels-avery-5164` | `label_sheet.tex` | `labels_avery_5164.yaml` |
| `labels-avery-15264` | `label_sheet.tex` | `labels_avery_5164.yaml` |
| `sticker-sheet` | `label_sheet.tex` | `sticker_sheet.yaml` |

## Style resolution

The Pandoc renderer sets `TEXMFHOME` to
`profiles/40_latex_import/styles/texmf` before invoking xelatex. This lets
LaTeX find style packages (`.sty` files) in the Foundry-owned TEXMF tree:

```
profiles/40_latex_import/styles/texmf/tex/latex/
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

## How to add or modify a profile

1. Add/edit the template in `profiles/40_latex_import/templates/`.
2. Add/edit the defaults YAML in `profiles/40_latex_import/defaults/`.
3. Add/edit assets under `profiles/40_latex_import/assets/`.
4. Add/update the resolver mapping if the profile ID does not map by convention.
5. Add a test fixture in `fixtures/sources/` and/or `fixtures/manifests/`.
6. Run `python3.14 -m cli doc <fixture> --profile <new-profile>` to validate.

## Known gaps

Profiles with no Foundry-owned template/default are reported as missing rather
than silently falling through to an external profile tree. That makes ownership
explicit: copy/import the needed surface first, then modify and render locally.

The local imported `mythic-letter-johannah` template carries bundle compatibility
support (`\tightlist`, longtable/booktabs/array, and a `$if(toc)$`-guarded TOC
slot) directly in Optical Foundry's profile copy.

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
- `defaults_found` — resolved path to defaults YAML under `profiles/40_latex_import/defaults/`
- `template_found` — resolved path to template `.tex` under `profiles/40_latex_import/templates/`
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

## Elian placeholder asset posture

Local imported Elian defaults now point to OF-owned synthetic placeholder art in
`fixtures/assets/elian/` for **local test renders only**:
- `elian_packet_cover_placeholder.png`
- `elian_poster_placeholder.png`

These defaults set `placeholder_assets: true`, and PandocRenderer copies that
into render evidence as:
- warning: synthetic placeholder asset note
- `boundary.placeholder_assets = true`
- `boundary.production_output = false`

`foundry profiles` still reports `elian-packet` and `elian-poster` as
**incompatible** for real bundle/content usage because real campaign art remains
external/content-dependent.
