# Sticker Sheet Contract — Optical Foundry

## Purpose

The sticker sheet pipeline renders a `sticker_sheet` render manifest subtype into a full-page sticker grid PDF with optional cut lines. Individual sticker cells may point to Markdown snippets/assets, but the sheet itself is manifest-driven.

## Input Shape

A sticker-sheet YAML manifest:

```yaml
kind: sticker_sheet
schema_version: sticker_sheet_v1
sheet_id: codex-zero-stickers
profile: sticker_sheet
layout:
  grid: [3, 3]
  cell_size: [2.5, 2.5]
  show_cut_lines: true
  cut_line_style: dashed
cells:
  - position: [0, 0]
    content: "Sticker 1"
    image: assets/icon1.png
  - position: [1, 0]
    source: stickers/sticker2.md
    image: assets/icon2.png
  - position: [0, 1]
    content: "Sticker 3"
  # ... remaining cells
```

A cell may contain inline content for simple sheets or point to a Markdown source
when the sticker has its own authored object.

## Profile

```yaml
# profiles/stickers/sticker_sheet.yaml
profile_id: sticker_sheet
profile_class: sticker
template: label_sheet.tex
pandoc_defaults:
  variables:
    layout: sticker
    grid_columns: 3
    grid_rows: 3
    cell_width_in: 2.5
    cell_height_in: 2.5
    show_cut_lines: true
```

## Rendering Flow

```
sticker_sheet.yaml → StickerSheetManifestCompiler.prepare()
  ├── Parse sticker_sheet manifest
  ├── Validate grid declaration
  ├── Validate cell positions (within grid bounds)
  └── Check for duplicate positions

→ StickerSheetRenderer.assemble_pandoc_args()
  ├── Generate intermediate LaTeX:
  │   ├── TikZ grid for sticker positions
  │   ├── Per-cell content groups
  │   └── Optional cut lines
  ├── Build PandocInvocation with label_sheet.tex template
  └── Set resource paths

→ PandocEngine.run()
  └── Execute Pandoc → sticker_sheet.pdf

→ StickerSheetRenderer.generate_evidence()
  ├── PDF hash, pages, bytes
  ├── Cell fill rate
  └── Text extraction
```

## Grid Positioning

Unlike labels (which use physical sheet specs), sticker sheets declare their
grid in the sheet manifest. This is intentional:

- **Labels**: Physical stock → sheet spec (data file)
- **Stickers**: Flexible layout → content declaration (frontmatter)

This separation keeps the label pipeline precise (matching physical stock)
while keeping stickers flexible (experimental layouts).

## Gap Resolution

This contract resolves the Stage 05 G4 (sticker-sheet-no-grid-layout) and
G6 (label-grid-positioning-source) gaps:

- **G4**: StickerSheetRenderer generates TikZ grid from frontmatter declaration
- **G6**: Grid positioning is declared in manifests/sheet specs, not baked
  into Markdown content as raw LaTeX

Content authors write Markdown. The renderer handles grid placement.
