---
uid: 019def23-7a00-7a00-8a00-000000000001
kind: note
note_role: architecture-design
validation_profile: standard
status: active
created: 2026-05-03T20:17:00-04:00
updated: 2026-05-12T12:01:51-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry — Greenfield Architecture Design"
summary: >
  Greenfield architecture for Optical Foundry: Pandoc-driven render engine
  with profile registry, render dispatch, typed render manifests, projection plans,
  bundle assembly, label/sticker manifests, and expansion contract. 40_latex preserved as known-good reference.
tags:
  - optical-foundry
  - greenfield
  - architecture
  - pandoc
  - render-pipeline
  - design
---

# Optical Foundry — Greenfield Architecture Design

## Runtime status — 2026-05-12

This design has a working local implementation surface. The current operational entrypoint is:

```bash
cd ~/Digital_Workspace/42_optical_foundry
python3.14 -m cli doc path/to/source.md --profile cam --output generated/<run-name>
python3.14 -m cli manifest manifests/<manifest>.yaml --output generated/manifests/<run-name>
```

Implemented surfaces include single-document rendering, typed manifest rendering, local `40_latex` profile imports, bundle-family assembly (`composite_bundle`, `cam_stack`, `codex_bundle`), title-page background controls, generated Mermaid/Vega/D2/Graphviz figure preprocessing, section dividers, and evidence sidecars. See `docs/IMPLEMENTATION_STATUS_2026-05-12.md` for the current code-change status.

The architectural boundary still holds: Foundry may read `40_latex` as a known-good reference/fallback, but normal Foundry renders must not mutate it.

---

## 0. Design Philosophy

Optical Foundry is a **Pandoc-driven render engine** that accepts
profile-annotated Markdown sources and produces styled PDF outputs.
The architecture is deliberately **profile-first**: every render path
begins and ends with a profile declaration. The core pipeline does not
hardcode which profiles exist; profiles declare themselves.

### Non-negotiable constraints

| Constraint | Reason |
|---|---|
| Pandoc remains the sole render engine | Proven reliability; all existing profiles depend on Pandoc YAML defaults + LaTeX templates |
| 40_latex stays read-only and untouched | Known-good reference for test input comparison and output fidelity |
| New folder, no mutation of 40_latex | Clean separation; greenfield proves itself independently |
| Same inputs, equivalent-or-better outputs | Backward compatibility with all existing profile source material |
| Expansion must not require core code changes | New profile = new YAML declaration + optional template/style, no pipeline edits |

### Vibe

The architecture should feel like a **foundry**: raw Markdown goes in,
a profile shapes it, Pandoc fires it, and a finished artifact comes out.
The forge metaphor carries through: profiles are the molds, render manifests are
the work orders, projection plans are the pour plans, and render dispatch is the pour.

---

## 0.5 Core Abstraction Split

Optical Foundry should distinguish **source truth**, **work/lifecycle state**,
**render intent**, **compiled projection**, and **rendered artifacts**.

The stable external inputs to Optical Foundry are:

1. **Markdown documents** — direct single-source render input.
2. **Render manifest files** — typed declarations for every recurring assembled,
   multi-source, physical-layout, or state-projection render case.

Manifests are the render target for anything more structured than a single
Markdown document. A manifest can point at a packet, a bundle/source graph, a
label run, a sticker sheet, the CAM Stack, Codex 0, or another render target that
recurs enough to deserve its own subtype.

| Layer | Meaning | Primary question | Examples |
|---|---|---|---|
| Markdown source document/object | Canonical content object and direct Foundry input | What is the content? | note, spec, letter, halo, report, canonical anchor |
| Render manifest | Machine-readable Foundry input declaring what should be rendered | What render target is being requested? | `label_run.yaml`, `sticker_sheet.yaml`, `cam_stack.yaml`, `codex_bundle.yaml`, `forge_packet_review.yaml` |
| Manifest subtype | Recurring contract for a specific render target family | How should this manifest be interpreted? | label run, sticker sheet, composite bundle, CAM Stack, Codex 0 bundle, Forge packet review |
| Bundle | Declarative content grouping/source graph | Which source objects belong together, in what order/roles, with what provenance? | Atrium context bundle, Codex 0 source bundle, evidence packet source graph |
| Packet / Marea-like work container | Stateful lifecycle container with goal, constraints, plan, state, evidence, questions, validation | What work exists and what governs it? | Forge packet assembling Codex 0, implementation packet, audit packet |
| Projection plan / assembly view | Internal compiled render IR produced from Markdown or a manifest | How exactly should this become an artifact? | resolved source list, generated reader guide, label grid, packet-state review view |
| Renderer | Mechanical backend adapter that turns a projection plan into Pandoc invocation(s) | How is it rendered? | PandocProjectionRenderer, LabelSheetRenderer internals, PDF evidence generator |
| Rendered artifact | Human-facing output with evidence sidecars | What can be read, printed, shared, or archived? | PDF, DOCX, HTML, EPUB, evidence JSON |

### Consequence for packets and bundles

A **bundle** is not a packet. It is a source graph/content grouping. It may be
assembled by a Forge packet, tracked by a packet, or rendered through a manifest,
but it does not own lifecycle governance.

A **packet** is not a bundle. It is a governed work container. A packet can
assemble the Codex 0 bundle by managing source files plus a `codex_bundle`
manifest. That same packet can also have a separate `forge_packet_review`
manifest that renders a projection of packet state: goals, constraints, progress,
questions, validation, and evidence. Those are different manifests because they
render different things.

Therefore packet review rendering should be modeled as:

```text
Forge packet directory/state
        ↓ forge_packet_review manifest
PacketReviewManifestCompiler
        ↓
ProjectionPlan / AssemblyView
        ↓
Pandoc-backed renderer
        ↓
Packet review artifact + evidence
```

Codex 0 bundle rendering should be modeled separately:

```text
Codex 0 source files + codex_bundle manifest
        ↓ CodexBundleManifestCompiler
ProjectionPlan / AssemblyView
        ↓
Pandoc-backed renderer
        ↓
Codex 0 artifact + evidence
```

The packet can govern both processes, but the source bundle artifact and packet
state artifact remain distinct projections.

## 1. Folder Structure

```
42_optical_foundry/
│
├── DESIGN.md                         # This file — architecture design doc
├── README.md                         # Quickstart and operational overview
├── INDEX.md                          # Beam index
├── STATE.json                        # Beam state
│
├── profiles/                         # ★ Profile registry — the heart of the system
│   ├── INDEX.md                      # Profile catalog and conventions
│   ├── base.yaml                     # Schema: what a profile file looks like
│   │
│   ├── reports/                      # Document/packet profiles
│   │   ├── yugenbase.yaml            # Foundation aesthetic
│   │   ├── risk.yaml                 # Risk assessment
│   │   ├── technology.yaml           # Technology docs
│   │   ├── generic_report.yaml       # Minimal generic report
│   │   ├── convergence.yaml          # Convergence logs
│   │   ├── keeper.yaml               # Keeper captures
│   │   ├── mythic.yaml               # Mythic docs
│   │   ├── cam.yaml                  # Civic Architecture (CAM)
│   │   ├── creative.yaml             # Creative output
│   │   ├── prometheus_packet.yaml    # Forge packet review
│   │   ├── elian_packet.yaml         # Elian strategy packet
│   │   └── elian_poster.yaml         # Elian poster format
│   │
│   ├── letters/                      # Letter/stationery profiles
│   │   ├── personal_letter.yaml      # Personal letter
│   │   ├── mythic_letter.yaml        # Mythic letter
│   │   └── mythic_letter_johannah.yaml # Johannah variant
│   │
│   ├── resumes/                      # Resume pipeline
│   │   ├── resume_base.yaml          # Base resume profile
│   │   ├── resume_cv.yaml            # CV/long-form
│   │   └── resume_resume.yaml        # Compact resume
│   │
│   ├── labels/                       # Label sheet profiles
│   │   ├── labels_base.yaml          # Base label profile
│   │   └── labels_avery_5164.yaml    # Avery 5164 label layout
│   │
│   └── stickers/                     # Sticker sheet profiles
│       └── sticker_sheet.yaml        # Sticker sheet layout
│
├── templates/                        # LaTeX templates (Pandoc --template)
│   ├── base.tex                      # General document template
│   ├── generic_report.tex            # Generic report
│   ├── convergence.tex               # Convergence logs
│   ├── keeper.tex                    # Keeper captures
│   ├── mythic.tex                    # Mythic docs
│   ├── cam.tex                       # CAM documents
│   ├── personal_letter.tex           # Personal letters
│   ├── mythic_letter_johannah.tex    # Johannah-specific letter
│   ├── elian_packet.tex              # Elian packet
│   ├── elian_poster.tex              # Elian poster
│   ├── resume.tex                    # Resume/CV
│   ├── label_sheet.tex               # Label/sticker sheet layout
│   └── bundle.tex                    # Composite bundle template (NEW)
│
├── styles/                           # LaTeX styles/packages (TEXMFHOME)
│   └── texmf/
│       └── tex/latex/yugen/
│           ├── yugenbase.sty         # Foundation yugen style
│           ├── yugencam.sty          # CAM-specific style
│           └── yugenletter.sty       # Letter stationery style
│
├── assets/                           # Fonts, images, logos
│   ├── fonts/
│   │   └── cinzel/                   # Cinzel font for labels
│   ├── logos/
│   │   └── logo_oasis_cam.png        # CAM logo
│   └── figures/
│       └── cam_triad.png             # CAM triad diagram
│
├── engine/                           # ★ Core render engine (Python)
│   ├── __init__.py                   # Package init
│   ├── registry.py                   # Profile registry — loads profiles/ tree
│   ├── dispatch.py                   # Render dispatch — routes Markdown/manifests to compilers/renderers
│   ├── pandoc.py                     # Pandoc invocation (replaces pandoc_build.py)
│   ├── frontmatter.py                # Frontmatter extraction and variable promotion
│   ├── mermaid.py                    # Mermaid diagram rendering
│   ├── text_fix.py                   # Labelled-list normalization, glyph fixes
│   └── profiles.py                   # Profile dataclasses and validation
│
├── renderers/                        # ★ Render classes — one per output class
│   ├── __init__.py                   # Package init
│   ├── base.py                       # BaseRenderer ABC
│   ├── document.py                   # Single-document renderer (doc_pipeline)
│   ├── packet_review.py              # forge_packet_review manifest compiler -> assembly view
│   ├── label_sheet.py                # Label sheet from run manifest
│   ├── sticker_sheet.py              # Sticker sheet layout
│   └── bundle.py                     # Composite/codex/cam bundle manifest compiler
│
├── schemas/                          # Schema definitions (YAML)
│   ├── profile_v1.yaml               # Profile declaration schema
│   ├── render_manifest_v1.yaml       # Umbrella manifest envelope/schema conventions
│   ├── bundle_manifest_v1.yaml       # Composite/CAM/Codex bundle manifest schema
│   ├── label_run_v1.yaml             # Label run manifest schema
│   └── render_evidence_v1.yaml       # Render evidence/output schema
│
├── contracts/                        # ★ Expansion & assembly contracts
│   ├── EXPANSION.md                  # How to add a new profile
│   ├── BUNDLE_ASSEMBLY.md            # Bundle assembly contract
│   ├── LABEL_CONTRACT.md             # Label pipeline contract
│   └── STICKER_CONTRACT.md           # Sticker sheet contract
│
├── cli/                              # CLI entrypoints
│   ├── __init__.py
│   ├── main.py                       # `foundry render` — unified CLI
│   ├── profiles.py                   # `foundry profiles` — profile management
│   └── validate.py                   # `foundry validate` — validation
│
├── validators/                       # Validation tools
│   ├── __init__.py
│   ├── profile_validator.py          # Profile declaration validation
│   ├── manifest_validator.py         # Bundle manifest validation
│   ├── output_validator.py           # PDF output validation
│   └── evidence.py                   # Evidence generation
│
├── fixtures/                         # Test fixtures (synthetic inputs)
│   ├── sources/                      # Synthetic Markdown sources
│   │   ├── generic_test.md           # Generic test document
│   │   ├── letter_test.md            # Letter test
│   │   ├── resume_test.md            # Resume test
│   │   ├── report_test.md            # Report test
│   │   ├── cam_anchor_1.md           # CAM anchor source 1
│   │   ├── cam_anchor_2.md           # CAM anchor source 2
│   │   └── label_test.md             # Label test
│   ├── manifests/                    # Test bundle manifests
│   │   └── cam_stack_exemplar.bundle.yaml
│   └── runs/                         # Test label runs
│       └── avery_5164_test.label_run.yaml
│
├── tests/                            # Test suite
│   ├── test_registry.py
│   ├── test_dispatch.py
│   ├── test_document_renderer.py
│   ├── test_packet_review_renderer.py
│   ├── test_label_renderer.py
│   ├── test_sticker_renderer.py
│   ├── test_bundle_renderer.py
│   └── conftest.py
│
├── generated/                        # gitignored — render outputs
│   ├── .gitignore
│   ├── documents/
│   ├── packets/
│   ├── labels/
│   ├── stickers/
│   ├── bundles/
│   └── evidence/
│
├── docs/                             # Documentation
│   └── migration-notes.md            # Migration path from 40_latex
│
└── .gitignore
```

### Folder design rationale

**`profiles/`** is organized by **output class** (reports, letters, resumes, labels, stickers)
rather than by a flat defaults directory. This groups related profiles together
and makes the catalog scannable. Each profile is a self-contained YAML declaration.

**`engine/`** contains zero profile-specific knowledge. It loads profiles from the
registry, dispatches to renderers, and wraps Pandoc. It never hardcodes a profile name.

**`renderers/`** contains one class per **render archetype**. Each class knows how to
assemble its input class (single doc, multi-file packet, label sheet, sticker sheet,
composite bundle) into a Pandoc invocation. Renderers do not know about specific profiles;
they receive a loaded profile object from the dispatcher.

**`schemas/`** defines the contracts. Every YAML file in the system (profile declaration,
render manifest, bundle manifest, label run, sticker sheet, render evidence) has a schema here.

**`contracts/`** is documentation for expansion and assembly. This is where a human
reads how to add a new profile or wire a new bundle type.

**`fixtures/`** mirrors the input archetypes with synthetic test inputs, organized
by input type (sources, manifests, runs).

**`generated/`** is the output root. Each render class writes to its own subdirectory.

---

## 2. Profile System

### 2.1 Profile declaration schema

Every profile is a YAML file in `profiles/<class>/<name>.yaml`:

```yaml
# Schema: profile_v1
# Example: profiles/reports/risk.yaml

profile_id: risk
profile_name: "Risk Assessment Report"
profile_class: document              # layout/profile family; render target comes from Markdown input or manifest kind
profile_version: "1.0"

# ===== Pandoc defaults (merged into Pandoc --defaults) =====
pandoc_defaults:
  variables:
    documentclass: article
    papersize: letter
    fontsize: 11pt
    linestretch: 1.15
    yugenstyle: yugenbase
    pagestyle: "yugenRule"

# ===== Inheritance: profiles can stack =====
extends:
  - yugenbase                          # Inherit yugenbase defaults first

# ===== LaTeX template =====
template: base.tex                    # Relative to templates/

# ===== LaTeX style package =====
style_package: yugenbase              # Loaded via \usepackage in template

# ===== Resource requirements =====
requires:
  fonts: []                           # Font families needed
  styles: [yugenbase]                 # Style packages needed
  assets: []                          # Asset files needed

# ===== Output metadata =====
output:
  format: pdf
  default_extension: .pdf
  page_size: letter
  orientation: portrait

# ===== Profile metadata =====
metadata:
  category: reports
  tags: [risk, security, assessment]
  description: "Formal risk assessment report with yugen styling"
  suitable_for: [security_reports, risk_assessments, technical_audits]
```

### 2.2 Profile classes vs manifest kinds

Profile classes describe **layout/profile families**. They are not the primary
render-target taxonomy. The render target is either a Markdown document or a
manifest `kind` / `schema_version` pair.

| Input | Target discriminator | Compiler / renderer path | Output shape |
|---|---|---|---|
| Markdown file | source file extension + selected profile | Document compiler → projection plan → Pandoc renderer | Single document PDF |
| Manifest file | `kind` + `schema_version` | Manifest subtype compiler → projection plan → Pandoc renderer | Depends on manifest subtype |
| Label manifest | `kind: label_run` | LabelRunManifestCompiler / LabelSheetRenderer | Single physical label-sheet PDF |
| Sticker manifest | `kind: sticker_sheet` | StickerSheetManifestCompiler / StickerSheetRenderer | Single sticker-sheet PDF |
| Composite bundle manifest | `kind: composite_bundle` or subtype | BundleManifestCompiler | Single composite PDF |
| CAM Stack manifest | `kind: cam_stack` | CAMStackManifestCompiler, likely specialized bundle compiler | CAM Stack PDF + evidence |
| Codex 0 bundle manifest | `kind: codex_bundle` | CodexBundleManifestCompiler | Codex 0 artifact + evidence |
| Forge packet review manifest | `kind: forge_packet_review` | PacketReviewManifestCompiler | Packet-state review PDF + evidence |

A new manifest subtype should be introduced when a render case becomes more than
a one-off. One-off multi-source renders can use a generic composite/bundle
manifest; recurring artifacts such as CAM Stack and Codex 0 deserve named
manifest subtypes.

### 2.3 Profile inheritance

Profiles can extend other profiles. This replaces the hardcoded `defaults` lists
in `doc_pipeline.py`:

```yaml
# profiles/reports/cam.yaml
profile_id: cam
profile_class: document
extends:
  - yugenbase                         # Gets all yugenbase defaults
pandoc_defaults:                      # Overrides / additions
  variables:
    yugenstyle: yugencam              # Override yugenstyle
    pagestyle: "yugenRule"
    logo_path: assets/logos/logo_oasis_cam.png
    division: "Oasis CAM"
    tagline: "Civic architecture and governance"
template: cam.tex
style_package: yugencam
```

Inheritance resolves depth-first, with later declarations overriding earlier ones.
The registry flattens an inheritance chain into a single effective profile object.

### 2.4 Profile registry

`engine/registry.py` loads the entire `profiles/` tree on startup:

```python
class ProfileRegistry:
    """Loads and indexes all profile declarations."""

    def __init__(self, profiles_root: Path):
        self.profiles: dict[str, Profile] = {}
        self.by_class: dict[str, list[Profile]] = {}

    def load_all(self) -> None:
        """Walk profiles/ tree, load every .yaml, resolve inheritance."""

    def get(self, profile_id: str) -> Profile:
        """Return a resolved profile by ID."""

    def list_by_class(self, profile_class: str) -> list[Profile]:
        """Return all profiles of a given class."""

    def validate_all(self) -> list[str]:
        """Validate all profiles; return list of warnings/errors."""
```

The registry is the **single source of truth** for what profiles exist.
There is no hardcoded PROFILES dict anywhere.

### 2.5 Profile validation

`validators/profile_validator.py` validates:

1. **Schema conformance** — profile YAML matches `schemas/profile_v1.yaml`
2. **Inheritance resolution** — all `extends` targets exist and form no cycles
3. **Template existence** — `template` file exists in `templates/`
4. **Style existence** — `style_package` exists in `styles/`
5. **Asset existence** — all `requires.assets` paths resolve
6. **Default mergeability** — Pandoc defaults are valid YAML
7. **Class consistency** — profile class matches its directory location

---

## 3. Render Dispatch

### 3.1 Unified dispatch flow

```
User: foundry render input.md --profile risk
                    │
                    ▼
         ┌─────────────────────┐
         │   CLI (cli/main.py)  │
         └─────────┬───────────┘
                   │
                   ▼
         ┌─────────────────────┐
         │  Profile Registry    │  ← loads profile by ID, resolves inheritance
         │  (engine/registry)   │
         └─────────┬───────────┘
                   │ Profile object (flattened, validated)
                   ▼
         ┌─────────────────────┐
         │  Render Dispatch     │  ← profile.profile_class → renderer class
         │  (engine/dispatch)   │
         └─────────┬───────────┘
                   │ Renderer instance
                   ▼
         ┌─────────────────────┐
         │  Renderer.prepare()  │  ← assemble input: normalize MD, resolve assets
         └─────────┬───────────┘
                   │ Prepared input
                   ▼
         ┌─────────────────────┐
         │  Renderer.render()   │  ← build Pandoc command, run, collect output
         └─────────┬───────────┘
                   │ Rendered PDF
                   ▼
         ┌─────────────────────┐
         │  Evidence Generator   │  ← hash, page count, text extract, provenance
         └─────────┬───────────┘
                   │
                   ▼
              Output PDF + evidence JSON
```

### 3.2 Renderer base class

```python
# renderers/base.py

class BaseRenderer(ABC):
    """Abstract base for all renderers."""

    def __init__(self, profile: Profile, engine: PandocEngine):
        self.profile = profile
        self.engine = engine

    @abstractmethod
    def prepare(self, input_path: Path) -> PreparedInput:
        """Validate and prepare input for rendering."""

    @abstractmethod
    def assemble_pandoc_args(self, prepared: PreparedInput) -> PandocInvocation:
        """Build Pandoc invocation from prepared input + profile."""

    def render(self, input_path: Path, output_dir: Path) -> RenderResult:
        """Full render pipeline: prepare → assemble → invoke Pandoc → collect evidence."""
        prepared = self.prepare(input_path)
        invocation = self.assemble_pandoc_args(prepared)
        output = self.engine.run(invocation)
        evidence = self.generate_evidence(prepared, output)
        return RenderResult(output=output, evidence=evidence)

    def generate_evidence(self, prepared: PreparedInput, output: Path) -> RenderEvidence:
        """Generate provenance and validation evidence."""
```

### 3.3 Dispatch table

`engine/dispatch.py` first distinguishes **input class**:

```python
if input_path.suffix in {".md", ".markdown"}:
    compiler = MarkdownDocumentCompiler(profile=selected_profile)
else:
    manifest = load_manifest(input_path)
    compiler = MANIFEST_COMPILERS[(manifest.kind, manifest.schema_version)]
```

Manifest dispatch is keyed by manifest subtype, not by packet/bundle identity:

```python
MANIFEST_COMPILERS = {
    ("label_run", "label_run_v1"): LabelRunManifestCompiler,
    ("sticker_sheet", "sticker_sheet_v1"): StickerSheetManifestCompiler,
    ("composite_bundle", "bundle_manifest_v1"): BundleManifestCompiler,
    ("cam_stack", "bundle_manifest_v1"): CAMStackManifestCompiler,
    ("codex_bundle", "bundle_manifest_v1"): CodexBundleManifestCompiler,
    ("forge_packet_review", "packet_review_manifest_v1"): PacketReviewManifestCompiler,
}
```

Each compiler emits a `ProjectionPlan` / assembly view. The Pandoc-backed render
executor consumes that projection plan. Adding a new profile within an existing
layout family requires no code changes; adding a recurring render target means
adding a new manifest subtype/compiler.

### 3.4 Pandoc engine wrapper

`engine/pandoc.py` replaces `40_latex/pandoc_build.py`:

```python
@dataclass
class PandocInvocation:
    pandoc_bin: str = "pandoc"
    input_path: Path
    output_path: Path
    defaults_files: list[Path]         # --defaults files (merged in order)
    template_path: Path | None = None  # --template
    resource_path: list[str] | None = None
    extra_args: list[str] | None = None
    env_overrides: dict[str, str] | None = None
    working_dir: Path | None = None

class PandocEngine:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.templates = project_root / "templates"
        self.styles = project_root / "styles" / "texmf"
        self.assets = project_root / "assets"

    def run(self, invocation: PandocInvocation) -> Path:
        """Execute Pandoc. Returns path to output PDF."""
        # 1. Preprocess: render Mermaid blocks if present
        # 2. Preprocess: normalize labelled lists
        # 3. Assemble CLI command
        # 4. Run pandoc subprocess
        # 5. Return output path
```

---

## 4. Manifest-Based Assembly Contract

### 4.1 Bundle-family manifest schema

A bundle-family manifest is one manifest subtype. It declares multiple source
anchors, generated front/back matter, figures, and profile settings — assembled
into one styled PDF. Generic composite bundles, CAM Stack, and Codex 0 can share
this family while using distinct `kind` values when their contracts recur:

```yaml
# Schema: bundle_manifest_v1
# Example: manifests/cam_stack_exemplar.bundle.yaml

kind: composite_bundle          # or cam_stack / codex_bundle for recurring specialized contracts
schema_version: bundle_manifest_v1
bundle_id: cam-stack-exemplar-v0
bundle_name: "CAM Stack — Civic Architecture Packet"
profile: cam                           # Profile ID from profiles/ registry

# ===== Presentation metadata (for title page and reader guide) =====
presentation:
  title: "CAM Stack"
  subtitle: "Civic Architecture and Governance Architecture"
  authors: ["Luis Ramirez"]
  date: "2026-05-03"
  abstract: >
    A composite packet assembling CAM civic architecture anchors,
    generated reader guide, figures, and afterword into one styled PDF.

# ===== Source anchors (ordered) =====
sources:
  - uid: cam-economy-interface
    path: fixtures/sources/cam_anchor_1.md
    role: primary_anchor
    title: "Economy Interface Signal — Layered Hybrid Model"
    include_frontmatter: full
    order: 1

  - uid: cam-civic-abundance
    path: fixtures/sources/cam_anchor_2.md
    role: supporting_anchor
    title: "Civic Abundance Model"
    include_frontmatter: full
    order: 2

# ===== Generated front/back matter =====
generated:
  reader_guide:
    enabled: true
    title: "Reader Guide"
    sections:
      - "Purpose of this packet"
      - "How to read this document"
      - "Source inventory"

  afterword:
    enabled: true
    title: "Afterword — Synthesis and Invitation"
    content: >
      This packet assembles CAM architecture anchors for review.
      Each source has been independently authored and verified.
      Frontmatter is preserved for provenance.

# ===== Figures and illustrations =====
figures:
  - path: assets/figures/cam_triad.png
    caption: "CAM Triad: Civic Architecture Model"
    placement: dedicated_page
    after_source_order: 2

# ===== Render options =====
render:
  include_toc: true
  toc_depth: 3
  preserve_source_provenance: true
  text_integrity_check: true
  visual_page_samples: true
  page_sample_format: png

# ===== Validation requirements =====
validation:
  require_all_source_paths: true
  require_all_figure_paths: true
  require_unique_uids: true
  required_text_markers:
    - "Economy Interface Signal"
    - "Civic Abundance Model"
    - "CAM Triad"
```

### 4.2 Bundle assembly algorithm

The bundle-family manifest compiler implements:

```
BundleManifestCompiler.prepare(bundle_manifest.yaml):
  1. Parse and validate manifest against bundle_manifest_v1 schema
  2. Resolve profile from registry
  3. Verify all source paths exist
  4. Verify all figure paths exist
  5. Verify UID uniqueness
  6. Verify ordering consistency

BundleManifestCompiler.compile(bundle_manifest.yaml) → ProjectionPlan / assembled Markdown view:
  1. Generate title page block (from packet metadata)
  2. Generate reader guide block (from manifest.generated.reader_guide)
  3. Generate TOC placeholder (\tableofcontents)
  4. For each source in order:
     a. Read source Markdown
     b. Extract and preserve full frontmatter block
     c. Demote headings by 2 levels (for nesting)
     d. Add section header with source title
     e. Append source body
     f. If a figure has after_source_order matching this source:
        - Add figure page with caption
  5. Generate afterword block
  6. Generate provenance block (source paths, digests)
  7. Write assembled Markdown to temp file

Bundle-family render execution:
  1. assemble → temp_assembled.md
  2. Build PandocInvocation with:
     - input: temp_assembled.md
     - defaults: profile flattened pandoc_defaults
     - template: profile.template
     - resource_path: [project_root, sources_dir, assets]
  3. Execute Pandoc
  4. Generate evidence JSON
  5. Capture visual page samples
```

### 4.3 What "CAM Stack" means in this architecture

The CAM Stack is the reference exemplar for the `bundle` profile class.
It exercises the full bundle assembly contract:

- **CAM profile** (`profiles/reports/cam.yaml`) provides styling
- **Bundle manifest** lists CAM anchor sources + figures
- **Bundle renderer** assembles the composite Markdown
- **Pandoc** renders with `cam.tex` template + `yugencam.sty`

The same family will work for Keeper bundles, Civic bundles, CAM Stack, Codex 0,
or any future multi-source composite artifact. Use a generic `composite_bundle`
manifest for one-offs; create a named manifest subtype when the artifact family
recurs and needs dedicated validation or generated sections.

### 4.4 Bundle validation checklist

Bundle renderer evidence includes the 30-point checklist from Stage 06:

**Manifest validation (M-01 through M-08):**
- Manifest parses as valid YAML
- schema_version is `bundle_manifest_v1`
- All source paths resolve to existing files
- All figure paths resolve to existing files
- No duplicate UIDs
- No ordering collisions
- Profile resolves in registry
- At least one `primary_anchor` role source exists

**Output validation (O-01 through O-09):**
- Output PDF exists and is non-empty
- PDF is valid (opens/inspects cleanly)
- Page count matches evidence metadata
- PDF has expected page size
- TOC present with expected depth
- Expected text markers found via pdftotext
- All sources represented (section headers in text)
- All figures present in PDF
- Figures have captions in text extract

**Evidence validation (E-01 through E-08):**
- Provenance evidence JSON exists and parses
- Evidence references correct manifest path
- Evidence records source digests for every source
- Evidence records figure inventory
- Evidence records output PDF path, pages, bytes, SHA-256
- Evidence records render metadata (profile, command, tool versions)
- Text extract exists and is non-empty
- Visual page samples exist for cover, section-opens, final page

**Boundary validation (B-01 through B-04):**
- No 40_latex files modified
- Output confined to packet-local generated/
- No production/public output paths used
- No external services/accounts/vendors contacted

**Negative validation (N-01 through N-05):**
- Missing source path → validation error
- Missing figure path → validation error
- Duplicate UID → validation error
- Unknown profile → validation error
- No primary_anchor → validation error

---

## 5. Label Pipeline Contract

### 5.1 Label system architecture

Labels follow a **run manifest → many Markdown labels → one sheet PDF** pattern.
This is preserved from the current `label_pipeline.py` and formalized:

```
label_run.yaml
    │
    ├── sheet_spec: avery-5164
    ├── defaults: layout + typography
    └── labels:
        ├── slot 1 → source: path/to/label1.md
        ├── slot 2 → source: path/to/label2.md
        └── slot N → source: path/to/labelN.md
                │
                ▼
        LabelSheetRenderer
                │
                ▼
        Pandoc (label_sheet.tex template + TikZ grid)
                │
                ▼
        label_sheet.pdf (with cut lines, safe areas, per-label content)
```

### 5.2 Label run manifest schema

```yaml
# Schema: label_run_v1
# Example: fixtures/runs/avery_5164_test.label_run.yaml

kind: label_run
schema_version: label_run_v1
run_id: kitchen-inventory-tree-labels
profile: labels_avery_5164           # References profiles/labels/labels_avery_5164.yaml

sheet_spec: avery-5164               # References label_specs/avery-5164.yaml
output_name: kitchen_inventory_labels

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
    source: fixtures/sources/label_test.md
  - slot: 2
    source: fixtures/sources/label_test.md
    layout:
      rotate_deg: 90
```

### 5.3 Avery 5164 support

The `avery-5164` sheet spec defines 3 columns × 2 rows of 4" × 3.333" labels
on a US Letter page. This is the same physical geometry as `avery-15264` and
is maintained as a named alias.

Sheet specs live in `schemas/` adjacent data or in a `label_specs/` subdirectory:

```yaml
# label_specs/avery-5164.yaml (to be created from 40_latex reference)
spec_id: avery-5164
page_size: [8.5, 11]                 # inches
label_size: [4.0, 3.333]             # inches
grid: [3, 2]                         # columns × rows
margins: [0.25, 0.5, 0.25, 0.5]    # [left, right, top, bottom] inches
pitch: [4.0, 3.333]                  # [horizontal, vertical] pitch
corner_radius: 0.125                 # inches
```

### 5.4 Label renderer flow

The `LabelSheetRenderer` implements the existing `label_pipeline.py` logic:

1. Load run YAML and validate against schema
2. Load sheet spec
3. For each label slot, load the label Markdown
4. Parse per-label frontmatter for layout/typography/image overrides
5. Deep-merge: sheet defaults → run defaults → label overrides
6. Generate intermediate LaTeX with TikZ grid placement
7. Render through Pandoc with `label_sheet.tex` template
8. Collect evidence (slot fill rate, label content digests, text extraction)

### 5.5 Image layers

The image layer model (background/foreground images with normalized coordinates,
opacity, and rotation) is preserved identically from the current system.
Labels support:

```yaml
background_images:
  - path: ../images/leaf.png
    x: 0.52           # Normalized to label safe area width (left origin)
    y: 1.00           # Normalized to label safe area height (top origin)
    w: 0.48           # Image width relative to safe area width
    opacity: 0.9
```

---

## 6. Sticker Sheet Workflow

### 6.1 Sticker sheet architecture

Sticker sheets follow a different input shape than labels: a **single Markdown file**
with grid layout directives in frontmatter, rendered to a full-page sticker grid:

```
sticker_content.md
    │
    │  frontmatter declares:
    │  - grid: [columns, rows]
    │  - cell_size: [width, height]
    │  - content cells: per-cell text/images
    │
    ▼
StickerSheetRenderer
    │
    ▼
Pandoc (label_sheet.tex template with sticker grid)
    │
    ▼
sticker_sheet.pdf
```

### 6.2 Sticker sheet profile

```yaml
# profiles/stickers/sticker_sheet.yaml
profile_id: sticker_sheet
profile_name: "Sticker Sheet"
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

### 6.3 Sticker sheet content model

A sticker sheet source Markdown declares per-cell content:

```markdown
---
profile: sticker_sheet
layout:
  grid: [3, 3]
  cell_size: [2.5, 2.5]
cells:
  - position: [0, 0]
    content: "Sticker 1"
    image: assets/icon1.png
  - position: [1, 0]
    content: "Sticker 2"
    image: assets/icon2.png
  # ... remaining cells
---

# Sticker Sheet

Optional overall header content.
```

The `StickerSheetRenderer`:
1. Validates the grid declaration
2. Generates TikZ grid placement (same machinery as label sheet)
3. Places content in each cell via the LaTeX picture environment
4. Adds cut lines if `show_cut_lines` is true

### 6.4 Current G6 gap resolution

The existing Stage 05 gap report identifies G6: "label grid positioning source"
— unclear where grid definitions live. This greenfield architecture resolves it:

- **Sheet specs** define physical grid dimensions (columns, rows, cell sizes)
- **Label run manifests** define which labels occupy which slots
- **Label/sticker Markdown** defines per-cell content
- **TikZ generation** is handled by the renderer, not baked into content

Grid positioning is **declared in the run manifest** and **rendered by the
renderer's TikZ generator** — no raw LaTeX required in Markdown content.

---

## 7. Expansion Contract

### 7.1 How to add a new profile (no code change)

1. **Create a YAML file** in the appropriate `profiles/<class>/` directory:

```bash
# Adding a new report profile: "monthly_summary"
touch profiles/reports/monthly_summary.yaml
```

2. **Declare the profile**:

```yaml
profile_id: monthly_summary
profile_name: "Monthly Summary Report"
profile_class: document
extends:
  - yugenbase
pandoc_defaults:
  variables:
    yugenstyle: yugenbase
    pagestyle: "yugenPlain"
template: base.tex
metadata:
  category: reports
  tags: [monthly, summary]
  description: "Monthly summary report with clean layout"
```

3. **Register** — the profile is automatically discovered on next `foundry` run.
   No code changes required.

4. **Use**:

```bash
foundry render input.md --profile monthly_summary
```

### 7.2 How to add a new profile class (code change in one file)

If a new output archetype is needed (e.g., "calendar", "menu", "ticket"):

1. **Create a renderer** in `renderers/`:

```python
# renderers/calendar.py
class CalendarRenderer(BaseRenderer):
    def prepare(self, input_path: Path) -> PreparedInput: ...
    def assemble_pandoc_args(self, prepared: PreparedInput) -> PandocInvocation: ...
```

2. **Register in dispatch table** (`engine/dispatch.py`):

```python
RENDERER_REGISTRY["calendar"] = CalendarRenderer
```

3. **Add profile directory** (`profiles/calendars/`) and first profile.

No other files change. The profile system, registry, CLI, and validation
all work without modification.

### 7.3 How to add a new label sheet spec

```yaml
# label_specs/avery-18163.yaml
spec_id: avery-18163
page_size: [8.5, 11]
label_size: [4.0, 2.0]
grid: [2, 5]
margins: [0.25, 0.25, 0.5, 0.5]
pitch: [4.0, 2.0]
corner_radius: 0.125
```

Used in a label run:

```yaml
sheet_spec: avery-18163
```

The renderer discovers sheet specs dynamically. No code change.

### 7.4 Expansion surface summary

| What you want | What you change | Files touched |
|---|---|---|
| New profile in existing class | Add YAML to `profiles/<class>/` | 1 new file |
| New profile class | Add renderer + dispatch entry + profile YAML | 2-3 files |
| New label sheet spec | Add YAML spec file | 1 new file |
| New template variant | Add `.tex` to `templates/`, reference in profile | 1-2 files |
| New style package | Add `.sty` to `styles/`, reference in profile | 1-2 files |
| New render feature (e.g., watermark) | Modify renderer or Pandoc engine | 1-2 files |

---

## 8. Migration Path from 40_latex

### 8.1 What moves (reference-only, not copy)

| 40_latex artifact | Greenfield target | Notes |
|---|---|---|
| `defaults/*.yaml` | `profiles/<class>/*.yaml` | Each becomes a properly-declared profile with inheritance |
| `templates/*.tex` | `templates/*.tex` | Largely unchanged; `bundle.tex` is new |
| `styles/texmf/` | `styles/texmf/` | Vendored LaTeX styles, identical |
| `assets/` | `assets/` | Fonts, images, logos |
| `input/` | NOT moved | Input is external to the pipeline; fixtures provide synthetic test inputs |
| `doc_pipeline.py` | `cli/main.py` + `engine/` | Rewritten as profile-driven dispatch |
| `pandoc_build.py` | `engine/pandoc.py` | Rewritten as PandocEngine class |
| `packet_pipeline.py` | `renderers/packet_review.py` manifest compiler + shared projection helpers | Rewritten as `forge_packet_review` manifest compiler, not a generic packet-as-document renderer |
| `label_pipeline.py` | `renderers/label_sheet.py` | Rewritten with schema-validated run manifests |
| `label_sheet_build.py` | `renderers/label_sheet.py` | Integrated into LabelSheetRenderer |
| `markdown_label.py` | `engine/` or `renderers/label_sheet.py` | Integrated |
| `label_specs.py` | `label_specs/` loader | Preserved pattern, formalized |

### 8.2 What stays in 40_latex

- The entire existing tree — untouched, read-only reference
- `deliverables/` — historical output archive
- `calibration/` — print calibration sheets
- `legacy/` — legacy scripts
- `vita/` — vitae source and output
- `work/` — work-in-progress area
- `tests/` — existing test suite for regression comparison

### 8.3 Proven path

The Foundry-owned profile import validates by:

1. **Input parity**: Same Markdown source → Foundry-owned profile copy → Foundry output
   must remain visually stable against approved fixtures
2. **Profile ownership**: Each supported imported profile has a Foundry-owned
   defaults/template/style/asset surface under `profiles/40_latex_import/`
3. **Fixture-based regression**: Synthetic fixtures render through the Foundry
   profile surface without external profile-tree fallback
4. **Transition**: External profile-tree references are archival/import history,
   not active runtime dependencies

---

## 9. Workflow Coverage Validation

### 9.1 Current profile coverage

Every supported imported profile maps to a Foundry-owned profile surface:

| Imported profile | Foundry class | Foundry-owned location |
|---|---|---|
| `yugenbase.yaml` | base (extended by others) | `profiles/reports/yugenbase.yaml` |
| `risk.yaml` | document | `profiles/reports/risk.yaml` |
| `technology.yaml` | document | `profiles/reports/technology.yaml` |
| `generic_report.yaml` | document | `profiles/reports/generic_report.yaml` |
| `convergence.yaml` | document | `profiles/reports/convergence.yaml` |
| `keeper.yaml` | document | `profiles/reports/keeper.yaml` |
| `mythic.yaml` | document | `profiles/reports/mythic.yaml` |
| `cam.yaml` | document (also used by bundles) | `profiles/reports/cam.yaml` |
| `creative.yaml` | document | `profiles/reports/creative.yaml` |
| `prometheus_packet.yaml` | packet | `profiles/reports/prometheus_packet.yaml` |
| `elian_packet.yaml` | document | `profiles/reports/elian_packet.yaml` |
| `elian_poster.yaml` | document | `profiles/reports/elian_poster.yaml` |
| `personal_letter.yaml` | letter | `profiles/letters/personal_letter.yaml` |
| `mythic_letter.yaml` | letter | `profiles/letters/mythic_letter.yaml` |
| `mythic_letter_johannah.yaml` | letter | `profiles/letters/mythic_letter_johannah.yaml` |
| `resume_base.yaml` | resume | `profiles/resumes/resume_base.yaml` |
| `resume_cv.yaml` | resume | `profiles/resumes/resume_cv.yaml` |
| `resume_resume.yaml` | resume | `profiles/resumes/resume_resume.yaml` |
| `labels_base.yaml` | label | `profiles/labels/labels_base.yaml` |
| `labels_avery_5164.yaml` | label | `profiles/labels/labels_avery_5164.yaml` |
| `sticker_sheet.yaml` | sticker | `profiles/stickers/sticker_sheet.yaml` |

**Total: 21 profiles across 6 profile/layout families. Packet review is now a manifest subtype (`forge_packet_review`), not a peer document/profile class.**

### 9.2 Workflow coverage matrix

| Workflow | Input | Profile class | Renderer | Supported? | Novelty |
|---|---|---|---|---|---|
| Single doc (risk, tech, mythic, etc.) | 1 MD file | document | DocumentRenderer | ✅ | Standard |
| Letter (personal, mythic, Johannah) | 1 MD with variables | letter | DocumentRenderer | ✅ | Standard |
| Resume (base, CV, compact) | 1 MD resume | resume | DocumentRenderer | ✅ | Standard (wired via TEXINPUTS) |
| Packet review (Prometheus/Forge) | `forge_packet_review` manifest → packet dir/state | packet_review/profile family | PacketReviewManifestCompiler → ProjectionPlan → Pandoc renderer | ✅ | Specialized projection over work state |
| Elian packet/poster | 1 MD (specialty) | document | DocumentRenderer | ✅ | Standard |
| Label sheet (Avery 5164) | Run manifest → N MD | label | LabelSheetRenderer | ✅ | Formalized from existing |
| Sticker sheet | `sticker_sheet` manifest | sticker | StickerSheetManifestCompiler → StickerSheetRenderer internals | ✅ | Manifest-driven physical/flexible layout |
| CAM Stack bundle | `cam_stack` manifest → N MD + figures | bundle/profile family | CAMStackManifestCompiler → ProjectionPlan → Pandoc renderer | ✅ | **New — greenfield addition** |
| Atrium context object | 1 MD (context object) | document | DocumentRenderer | ✅ | Standard (generic_report) |
| Atrium context bundle | `composite_bundle` manifest → N MD | bundle/profile family | BundleManifestCompiler → ProjectionPlan → Pandoc renderer | ✅ | **New — unified with CAM Stack family** |

### 9.3 Gap resolution from Stage 05

| Gap ID | Description | Resolution in greenfield |
|---|---|---|
| G1 | tightlist-mythic-letter-johannah | Fixed in the Foundry-owned `mythic_letter_johannah.tex` profile copy |
| G2 | elian-campaign-asset-paths | Content-dependent; profile declares `requires.assets` for validation |
| G3 | resume-base-cv-orphan-wiring | Resume profiles wired via profile declaration, not hidden in doc_pipeline.py |
| G4 | sticker-sheet-no-grid-layout | StickerSheetManifestCompiler generates TikZ grid from `sticker_sheet` manifest declaration |
| G5 | labels-avery-5164-synthetic-layout | LabelSheetRenderer generates TikZ placement from sheet spec |
| G6 | label-grid-positioning-source | Grid defined in sheet spec + run manifest, rendered by renderer |
| G7 | mythic-letter-johannah-font-paths | Font paths in `requires.fonts` and `styles/`; resource-path includes font dirs |

### 9.4 Composite stack bundle validation

The CAM Stack exemplar exercises the bundle-family manifest contract:

1. **Manifest**: `fixtures/manifests/cam_stack_exemplar.bundle.yaml` uses `kind: cam_stack` and declares 2+ CAM anchor sources + 1 figure + reader guide + afterword
2. **Profile**: `profiles/reports/cam.yaml` provides CAM styling
3. **Assembly**: CAMStackManifestCompiler / bundle-family compiler generates a projection plan with reader guide, demoted source sections, figure pages, afterword
4. **Render**: Pandoc with `cam.tex` template + `yugencam.sty` style
5. **Evidence**: 30-point validation checklist, visual page samples, provenance JSON
6. **Boundary**: Output in `generated/bundles/`, 40_latex untouched

### 9.5 What's NOT yet designed (out of scope for this doc)

| Scope boundary | Reason |
|---|---|
| CLI implementation (argparse, subcommands) | Implementation phase — architecture sufficient |
| Oasis Mint printable-surface integration | Requires interface contract approval from Luis |
| Atrium Service/Core real integration | Requires Atrium API stability |
| Production deployment / CI | Post-validation phase |
| External service integration (cloud render, API) | Out of scope until Luis requests |
| Visual regression testing framework | Can be layered on after core renderers work |

---

## 10. Design Decisions Log

| ID | Decision | Rationale | Trade-offs |
|---|---|---|---|
| DD-01 | Profile-first architecture | No hardcoded profile lists; expansion is file creation, not code change | Startup cost of resolving inheritance chains |
| DD-02 | Manifest subtype taxonomy for render targets | Keeps packets/bundles/labels/stickers/CAM/Codex distinct while sharing projection/render machinery | Requires subtype schemas/compilers for recurring artifact families |
| DD-03 | YAML inheritance for profiles | Replaces hardcoded defaults lists; mirrors CSS/LaTeX precedent | Circular dependency detection needed |
| DD-04 | Intermediate Markdown for bundles | Pandoc speaks Markdown natively; assembly is simple concatenation | Large bundles may produce large intermediate files |
| DD-05 | TikZ for label/sticker grids | LaTeX's native grid placement; no external dependencies | Requires LaTeX picture/tikz knowledge for debugging |
| DD-06 | Separate sheet specs from profiles | Labels use physical stock specs + content profiles; they vary independently | Two files to maintain per label config |
| DD-07 | Render evidence as JSON sidecars | Machine-verifiable outputs; self-describing provenance | Additional I/O per render |
| DD-08 | Pandoc as sole engine (no secondary renderers) | Simplicity; all profiles use Pandoc already | Limits to Pandoc-supported output formats |
| DD-09 | Profile class directories | Navigable catalog; scannable at a glance | Slightly deeper directory nesting |
| DD-10 | generated/ as output root, gitignored | Clean separation of source and output; no .gitignore proliferation | Must document output locations |

---

## 11. Architecture Diagram

```
                         ┌──────────────────────────────────┐
                         │           CLI LAYER               │
                         │  foundry render                   │
                         │  foundry profiles                 │
                         │  foundry validate                 │
                         └──────────────┬───────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
          ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
          │   PROFILE    │    │   DISPATCH   │    │  VALIDATION  │
          │   REGISTRY   │◄───│   ENGINE     │───►│  ENGINE      │
          │              │    │              │    │              │
          │ Loads YAML   │    │ Maps class→  │    │ Profile      │
          │ Resolves     │    │ renderer     │    │ Manifest     │
          │ inheritance  │    │ Builds       │    │ Output       │
          └──────┬───────┘    │ Pandoc args  │    │ Evidence      │
                 │            └──────┬───────┘    └──────────────┘
                 │                   │
                 │    ┌──────────────┼──────────────┐
                 │    │              │              │
                 ▼    ▼              ▼              ▼
          ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
          │ DOCUMENT │ │ PACKET   │ │  LABEL   │ │ BUNDLE   │
          │ RENDERER │ │ RENDERER │ │ RENDERER │ │ RENDERER │
          └─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘
                │            │            │            │
                └────────────┼────────────┼────────────┘
                             │            │
                             ▼            ▼
                    ┌────────────────────────────┐
                    │       PANDOC ENGINE         │
                    │                            │
                    │  Preprocess (Mermaid,       │
                    │  labelled lists)            │
                    │  Assemble CLI command       │
                    │  Execute Pandoc             │
                    │  Collect output             │
                    └────────────┬───────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
              ┌─────────┐ ┌─────────┐ ┌─────────┐
              │TEMPLATES│ │ STYLES  │ │ ASSETS  │
              │ (.tex)  │ │ (.sty)  │ │(fonts,  │
              │         │ │         │ │ images) │
              └─────────┘ └─────────┘ └─────────┘
                                 │
                                 ▼
                    ┌────────────────────────────┐
                    │         OUTPUT              │
                    │                            │
                    │  generated/documents/*.pdf  │
                    │  generated/packets/*.pdf    │
                    │  generated/labels/*.pdf     │
                    │  generated/stickers/*.pdf   │
                    │  generated/bundles/*.pdf    │
                    │  generated/evidence/*.json  │
                    └────────────────────────────┘
```

---

## 12. Next Steps (not part of this design doc)

This design doc is the architecture. Implementation phases:

1. **Phase 0 — Scaffold**: Create folder structure, `__init__.py` files, `.gitignore`
2. **Phase 1 — Profile Registry**: `engine/registry.py` with YAML loader, inheritance resolver, validator
3. **Phase 2 — Pandoc Engine**: `engine/pandoc.py` with Mermaid, list normalization, Pandoc invocation
4. **Phase 3 — Document Renderer**: `renderers/document.py` + `renderers/base.py` — render single docs through any profile
5. **Phase 4 — CLI**: `cli/main.py` with `foundry render` subcommand
6. **Phase 5 — Profile Migration**: Create all 21 profile YAMLs in `profiles/`
7. **Phase 6 — Validation Gate**: Run all profiles against synthetic fixtures; compare output to 40_latex
8. **Phase 7 — Label Renderer**: `renderers/label_sheet.py` with run manifest support
9. **Phase 8 — Sticker Renderer**: `renderers/sticker_sheet.py`
10. **Phase 9 — Projection Plan Model**: shared assembly-view data structures for object, bundle, and packet-review projections
11. **Phase 10 — Bundle Renderer**: `renderers/bundle.py` with composite stack/context-bundle assembly
12. **Phase 11 — Packet Review Adapter**: `renderers/packet_review.py` converts Forge packet state into an assembly view and delegates shared rendering behavior
13. **Phase 12 — CAM Stack Exemplar**: Render CAM Stack through bundle renderer; validate 30-point checklist
14. **Phase 13 — Retirement Plan**: Once greenfield proves equivalent-or-better for all profiles, archive 40_latex

---

## Appendix A: Profile Declaration Template

```yaml
# Copy this template to create a new profile
# Save as: profiles/<class>/<profile_id>.yaml

profile_id: ""                         # REQUIRED: unique identifier
profile_name: ""                       # Human-readable name
profile_class: document                # document | letter | resume | label | sticker | bundle
profile_version: "1.0"

# Inheritance chain (resolved depth-first)
extends:
  - yugenbase                          # Base profile(s) to inherit from

# Pandoc defaults — merged into pandoc --defaults
pandoc_defaults:
  variables:
    papersize: letter
    fontsize: 11pt
    linestretch: 1.15
  metadata:
    lang: en-US

# LaTeX template (relative to templates/)
template: base.tex

# LaTeX style package loaded via \usepackage
style_package: ""

# Required resources (validated at load time)
requires:
  fonts: []
  styles: []
  assets: []

# Output expectations
output:
  format: pdf
  default_extension: .pdf
  page_size: letter
  orientation: portrait

# Documentation
metadata:
  category: ""
  tags: []
  description: ""
  suitable_for: []
```

## Appendix B: Bundle Manifest Template

```yaml
# Copy this template to create a new bundle-family render manifest
# Save as: manifests/<bundle_name>.bundle.yaml

kind: composite_bundle   # or cam_stack / codex_bundle for recurring specialized contracts
schema_version: bundle_manifest_v1
bundle_id: ""
bundle_name: ""
profile: ""                           # Profile ID from profiles/ registry

presentation:
  title: ""
  subtitle: ""
  authors: []
  date: ""
  abstract: ""

sources:
  - uid: ""
    path: ""
    role: primary_anchor
    title: ""
    include_frontmatter: full
    order: 1

generated:
  reader_guide:
    enabled: true
    title: "Reader Guide"
    sections: []
  afterword:
    enabled: true
    title: "Afterword"
    content: ""

figures:
  - path: ""
    caption: ""
    placement: dedicated_page
    after_source_order: 1

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
  required_text_markers: []
```
