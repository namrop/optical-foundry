# Expansion Contract — Optical Foundry

How to grow the Optical Foundry profile system without modifying core pipeline code.

## Rule of Thumb

**If you're adding a new profile in an existing class, you touch one file.**
**If you're adding a new profile class, you touch two files plus one renderer.**

## Scenario 1: New Profile (Existing Class)

You want a "monthly_summary" report profile with slightly different defaults.

### Step 1: Create the profile YAML

```bash
touch profiles/reports/monthly_summary.yaml
```

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
    fontsize: 10pt
template: base.tex
metadata:
  category: reports
  tags: [monthly, summary]
  description: "Monthly summary report with clean layout"
```

### Step 2: Use it

```bash
foundry render input.md --profile monthly_summary
```

That's it. The registry discovers it automatically. No code changes.

### Optional: Custom template

If the existing templates don't match, create a new one:

```bash
touch templates/monthly_summary.tex
```

Then reference it in the profile:

```yaml
template: monthly_summary.tex
```

### Optional: Custom style

Create a style package:

```bash
touch styles/texmf/tex/latex/yugen/yugenmonthly.sty
```

Reference it:

```yaml
style_package: yugenmonthly
requires:
  styles: [yugenmonthly]
```

## Scenario 2: New Profile Class

You want a "calendar" renderer that places events in a grid.

### Step 1: Create the renderer

```python
# renderers/calendar.py

from renderers.base import BaseRenderer, PreparedInput, PandocInvocation, RenderResult

class CalendarRenderer(BaseRenderer):
    def prepare(self, input_path: Path) -> PreparedInput:
        # Parse calendar YAML, validate grid
        ...

    def assemble_pandoc_args(self, prepared: PreparedInput) -> PandocInvocation:
        # Generate TikZ grid with events
        ...
```

### Step 2: Register in dispatch

In `engine/dispatch.py`:

```python
RENDERER_REGISTRY["calendar"] = CalendarRenderer
```

### Step 3: Create profile directory and first profile

```bash
mkdir profiles/calendars
touch profiles/calendars/monthly_calendar.yaml
```

```yaml
profile_id: monthly_calendar
profile_name: "Monthly Calendar"
profile_class: calendar
template: calendar.tex
pandoc_defaults:
  variables:
    papersize: letter
    orientation: landscape
    grid_columns: 7
    grid_rows: 5
```

### Step 4: (Optional) Create template

```bash
touch templates/calendar.tex
```

That's it. No changes to registry.py, cli/main.py, validators, or engine — they all
discover the new class dynamically.

## Scenario 3: New Label Sheet Spec

You bought a different label stock and need a new sheet spec.

### Step 1: Create the spec

```yaml
# label_specs/my-new-labels.yaml
spec_id: my-new-labels
page_size: [8.5, 11]
label_size: [2.625, 1.0]
grid: [3, 10]
margins: [0.1875, 0.1875, 0.5, 0.5]
pitch: [2.75, 1.0]
corner_radius: 0.125
```

### Step 2: Use in a run manifest

```yaml
sheet_spec: my-new-labels
```

The renderer loads sheet specs dynamically. No code change.

## Scenario 4: New Bundle Type

You want a "Keeper Stack" bundle that assembles multiple Keeper captures.

### Step 1: Create the bundle manifest

```yaml
# manifests/keeper_stack.bundle.yaml
kind: composite_stack_packet
schema_version: bundle_manifest_v1
bundle_id: keeper-stack-v0
bundle_name: "Keeper Stack"
profile: keeper
packet:
  title: "Keeper Stack — Governance Anchors"
sources:
  - uid: keeper-capture-1
    path: sources/k1.md
    role: primary_anchor
    order: 1
  # ... more keeper sources
```

### Step 2: Render

```bash
foundry render manifests/keeper_stack.bundle.yaml --output keeper_stack.pdf
```

No code changes — `BundleRenderer` handles any profile in the `bundle` class.
The `keeper` profile provides styling.

## When Core Code Changes ARE Required

| Situation | What changes | Files |
|---|---|---|
| New Pandoc feature (e.g., markdown extension) | `engine/pandoc.py` | 1 file |
| New render archetype (e.g., slides) | New renderer class + dispatch entry | 2 files |
| New validation category | `validators/` | 1 file |
| CLI argument changes | `cli/main.py` | 1 file |
| Profile schema changes | `schemas/profile_v1.yaml` + registry loader | 2 files |
| New evidence format | `schemas/render_evidence_v1.yaml` + evidence generator | 2 files |

## Profile Inheritance Rules

1. **Stack order**: `extends` list is resolved depth-first, left-to-right.
   Later profiles override earlier ones.
2. **Merge semantics**: Pandoc `variables` are shallow-merged.
   List fields (e.g., `requires.fonts`) are concatenated with deduplication.
3. **Circular detection**: The registry detects and rejects circular `extends` chains.
4. **Missing parent**: If an `extends` target doesn't exist, the registry reports
   the missing profile and rejects the load.

## Profile Validation

Every profile is validated at load time:

1. Schema conformance (matches `schemas/profile_v1.yaml`)
2. Inheritance chain resolves (no cycles, all parents exist)
3. Template file exists in `templates/`
4. Style package exists in `styles/` (if declared)
5. Required assets exist (if declared)
6. Required fonts exist (if declared)
7. Profile class has a matching renderer in the dispatch table
8. Profile ID is unique across all profiles
9. Profile class matches its directory (e.g., `profiles/reports/*.yaml` must have `profile_class: document`)

Validation failures prevent rendering. Warnings allow rendering but are reported.

## Versioning

- **Profile version**: Each profile has a `profile_version` field. Bump when defaults change.
- **Schema version**: Schema files are versioned (e.g., `profile_v1`, `profile_v2`).
  The registry reads the schema version from the profile and routes to the correct parser.
- **Backward compatibility**: Old profiles with old schema versions should continue to work
  until explicitly deprecated.
