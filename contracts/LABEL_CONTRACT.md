# Label Pipeline Contract — Optical Foundry

## Purpose

The label pipeline produces printable label-sheet PDFs from a run manifest
that places independent Markdown label sources into physical sheet slots.

## Input Shape

A label run YAML manifest:

```yaml
kind: label_run
schema_version: label_run_v1
run_id: my-label-run
profile: labels_avery_5164           # References profiles/labels/labels_avery_5164.yaml

sheet_spec: avery-5164               # References label_specs/avery-5164.yaml
output_name: my_labels

defaults:
  layout:
    text_align: left
    safe_inset_in: 0.24
    top_padding_in: 0.12
  typography:
    title:
      font_family: cinzel
      font_size_pt: 26
      leading_pt: 30
    subtitle:
      font_family: cinzel
      font_size_pt: 10
      leading_pt: 12
    body:
      font_family: sans
      font_size_pt: 8
      leading_pt: 10

labels:
  - slot: 1
    source: path/to/label1.md
  - slot: 2
    source: path/to/label2.md
    layout:
      rotate_deg: 90
```

## Label Markdown Format

Each label is a Markdown file with YAML frontmatter:

```markdown
---
title: "Label Title"
kind: note
label_id: unique.label.id
layout:
  text_align: left
background_images:
  - path: ../images/icon.png
    x: 0.52
    y: 1.00
    w: 0.48
    opacity: 0.9
---

# Title

## Subtitle

\vspace*{3\baselineskip}

- item 1
- item 2

\vfill

*Fun fact italic text*
```

## Sheet Specs

Sheet specs define physical label stock geometry:

```yaml
spec_id: avery-5164
page_size: [8.5, 11]                 # inches
label_size: [4.0, 3.333]
grid: [3, 2]
margins: [0.25, 0.5, 0.25, 0.5]
pitch: [4.0, 3.333]
corner_radius: 0.125
```

## Rendering Flow

```
run.yaml → LabelSheetRenderer.prepare()
  ├── Parse run YAML
  ├── Load sheet spec
  ├── For each label slot:
  │   ├── Load label Markdown
  │   ├── Parse frontmatter
  │   └── Deep-merge: spec defaults → run defaults → label overrides
  └── Validate: all slots filled, all sources exist

→ LabelSheetRenderer.assemble_pandoc_args()
  ├── Generate intermediate LaTeX:
  │   ├── TikZ grid for each label position
  │   ├── Per-label content group
  │   ├── Image layers (background/foreground)
  │   └── Rotation transforms
  ├── Build PandocInvocation with label_sheet.tex template
  └── Set resource paths

→ PandocEngine.run()
  └── Execute Pandoc → label_sheet.pdf

→ LabelSheetRenderer.generate_evidence()
  ├── PDF hash, pages, bytes
  ├── Slot fill rate
  ├── Per-label content digests
  └── Text extraction
```

## Image Layer Model

Labels support background and foreground image layers with normalized coordinates:

| Parameter | Range | Description |
|---|---|---|
| `x` | 0-1 | Left origin, normalized to safe area width |
| `y` | 0-1 | Top origin, normalized to safe area height |
| `w` | 0-1+ | Image width relative to safe area width |
| `opacity` | 0-1 | Image transparency |
| `rotate_deg` | 0-360 | Rotation in degrees |

## Avery 5164 Support

Avery 5164 is a compatibility alias for Avery 15264 (3 columns × 2 rows,
4" × 3.333" labels on US Letter). The sheet spec loader resolves it to
the canonical spec.

## Debug Mode

`--debug-lines` flag draws:
- Outer physical label boundary (solid)
- Inner safe-area boundary (dashed)

Use for alignment and layout review. Disable for live printing.
