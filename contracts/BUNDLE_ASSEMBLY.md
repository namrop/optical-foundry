# Bundle-Family Manifest Assembly Contract — Optical Foundry

## Purpose

A bundle-family render manifest assembles multiple independent Markdown sources,
generated front/back matter, figures, and profile styling into a single styled
artifact. Generic composite bundles, CAM Stack, and Codex 0 are all members of
this family when they render source graphs into human-facing artifacts.

## Boundary with Packets and Documents

A **source document** is a single canonical content object. A **bundle** is a
declarative assembly/source graph over one or more source documents. A **packet**
is a stateful work/lifecycle container with goals, constraints, state, evidence,
and validation surfaces.

The render target for bundle-family output is a manifest, not the bundle concept
itself. A Forge packet can govern or produce a bundle manifest, but the packet is
not the bundle. Packet review rendering uses a separate `forge_packet_review`
manifest that projects packet state; it should not be conflated with the source
files and manifest used to render the artifact the packet is building.

## Input Shape

A YAML render manifest following the bundle-family schema `schemas/bundle_manifest_v1.yaml`:

```yaml
kind: composite_bundle              # or cam_stack / codex_bundle for recurring specialized cases
schema_version: bundle_manifest_v1
bundle_id: unique-bundle-id
bundle_name: "Human-Readable Name"
profile: cam                            # References profiles/reports/cam.yaml

presentation:
  title: "Packet Title"
  subtitle: "Optional Subtitle"
  authors: ["Author Name"]
  date: "YYYY-MM-DD"
  abstract: "Short description"

sources:
  - uid: unique-source-id
    path: path/to/source.md
    role: primary_anchor | supporting_anchor | appendix | reference
    title: "Display Title"
    include_frontmatter: full | summary | none
    order: 1

section_dividers:
  - uid: evidence-divider
    before_source_uid: evidence-source
    title: "Evidence Field"
    subtitle: "Local strain, legitimacy, and civic coordination"
    body: "Optional one-paragraph orientation for this section."
  - uid: designed-divider
    before_source_order: 4
    source:
      path: path/to/designed_section_title_page.md
      include_frontmatter: none

generated:
  reader_guide:
    enabled: true
    title: "Reader Guide"
    sections:
      - "Purpose"
      - "How to Read"
  afterword:
    enabled: true
    title: "Afterword"
    content: "Synthesis text"

figures:
  - path: path/to/figure.png
    caption: "Figure caption"
    placement: dedicated_page | near | section_open | end_of_packet
    after_source_order: 2

render:
  include_toc: true
  toc_depth: 3
  preserve_source_provenance: true
  text_integrity_check: true
  visual_page_samples: true
  page_sample_format: png

validation:
  require_all_source_paths: true
  require_all_figure_paths: true
  require_unique_uids: true
  required_text_markers:
    - "Expected text in output"
```

## Assembly Algorithm

```
1. PARSE & VALIDATE
   ├── Parse YAML manifest
   ├── Validate against bundle_manifest_v1 schema
   ├── Resolve profile from registry
   ├── Verify all source paths exist
   ├── Verify all figure paths exist
   ├── Verify UID uniqueness
   └── Verify ordering consistency

2. ASSEMBLE INTERMEDIATE MARKDOWN
   ├── Title page block (from packet metadata)
   │   ├── Title, subtitle, authors, date
   │   └── Abstract block
   ├── Reader guide block (if enabled)
   │   ├── Generated section headers
   │   └── Source inventory table
   ├── \newpage + \tableofcontents (if render.include_toc)
   │
   ├── For each source (ordered by sources[].order):
   │   ├── Section divider pages targeting this source (if any)
   │   │   ├── Generic divider page from manifest title/subtitle/body; or
   │   │   └── Source-backed divider page from section_dividers[].source.path
   │   ├── \newpage
   │   ├── Source section header (## Source Title)
   │   ├── Frontmatter block (if include_frontmatter != none)
   │   │   ├── Raw YAML code block (full)
   │   │   └── Parsed key-value table (summary)
   │   ├── Source body content
   │   │   ├── Strip original frontmatter
   │   │   ├── Demote headings by 2 levels
   │   │   └── Normalize glyphs (→ to ->, etc.)
   │   └── Figure pages (for figures with after_source_order matching)
   │       ├── \newpage
   │       ├── Figure image
   │       └── Figure caption
   │
   ├── Afterword block (if enabled)
   │   ├── \newpage
   │   └── Generated afterword content
   │
   └── Provenance block
       ├── Source inventory (paths, UIDs, digests)
       ├── Figure inventory
       └── Render metadata

3. RENDER
   ├── Write intermediate Markdown to temp file
   ├── Build PandocInvocation:
   │   ├── input: temp_assembled.md
   │   ├── defaults: profile.flattened_pandoc_defaults
   │   ├── template: profile.template
   │   ├── resource_path: [project_root, sources_dir, assets_dir]
   │   └── env: TEXMFHOME, TEXINPUTS
   ├── Execute Pandoc
   └── Collect output PDF

4. GENERATE EVIDENCE
   ├── PDF hash (SHA-256), page count, byte size
   ├── pdftotext extraction
   ├── Text marker verification
   ├── Figure presence verification
   ├── Visual page samples (cover, sections, final)
   ├── Provenance JSON sidecar
   └── Boundary assertions (40_latex clean, generated/ only)
```

## Output Artifacts

| Artifact | Path | Format |
|---|---|---|
| PDF | `generated/bundles/{bundle_id}.pdf` | PDF |
| Evidence | `generated/evidence/{bundle_id}_evidence.json` | JSON |
| Text extract | `generated/evidence/{bundle_id}_text.txt` | UTF-8 |
| Page samples | `generated/evidence/{bundle_id}_p{N}.png` | PNG |

## Validation Checklist

The 30-point checklist from the Stage 06 composite stack design is the
validation contract for bundle outputs. See `DESIGN.md` §4.4.

## Profile Independence

The bundle renderer is profile-agnostic. It receives a resolved profile
object from the dispatch engine and uses its Pandoc defaults, template,
and styles. Any `bundle`-class profile works identically.

This means:
- CAM Stack → `profile: cam` → `cam.tex` template → `yugencam.sty` style
- Keeper Stack → `profile: keeper` → `keeper.tex` template → `yugenbase.sty`
- Generic bundle → `profile: generic_report` → `generic_report.tex` template
