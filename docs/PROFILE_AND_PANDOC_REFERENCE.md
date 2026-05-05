# Optical Foundry — Profile and Pandoc Reference Wiring

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

The `mythic-letter-johannah` template has a known `\tightlist` gap
documented in the packet. This is a target `40_latex` mutation and requires
explicit Luis approval.
