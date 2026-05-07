# Render Resolver and Profile Spine Refactor Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Refactor Optical Foundry so profile rendering is driven by a single resolver and a neutral long-form document spine, while preserving divergent artifact lines for mythic letters, labels/stickers, and future Atrium context-object renderers, while keeping manifest/bundle families separate from document profile families.

**Architecture:** Replace duplicated profile facts with a single profile resolver that compiles each render into an explicit profile stack, template, asset/resource environment, and boundary evidence. Split the current Yugen-derived report DNA into a neutral long-form document spine plus brand/skin overlays (`tech`, `risk`, etc.). Keep one-off art/stationery profiles separate from ordinary document profiles, and keep bundle/packet-review/physical-sheet assembled artifacts as manifest families rather than pretending they are document profiles.

**Tech Stack:** Python 3.14, Pandoc, XeLaTeX, local imported 40_latex assets under `profiles/40_latex_import/`, pytest, existing `ProjectionPlan`, `PandocRenderer`, and CLI.

---

## Architectural Decisions Captured

### 1. Neutral long-form document spine

The current `tech` / `risk` / `creative` stack contains the closest working model for ordinary long-form Atrium PDFs: typography, headers/footers, TOC, longtable handling, section spacing, image sizing, and Pandoc compatibility. The refactor should extract that shared DNA into a less-Yugen-themed base.

Target concept:

```text
profiles/40_latex_import/defaults/
  document_spine.yaml          # neutral long-form defaults
  atrium_report.yaml           # default Atrium document/report skin
  yugen_tech.yaml              # Yugen-branded tech skin
  yugen_risk.yaml              # Yugen-branded risk skin
  yugen_creative.yaml          # Yugen-branded creative skin
```

Do not remove legacy profile IDs immediately. Keep aliases / compatibility names:

```text
tech      -> yugen_tech
risk      -> yugen_risk
creative  -> yugen_creative
```

### 2. Profile families and manifest families are separate axes

Profiles should be classified by render family for **individual documents/objects**:

- `document_spine`: ordinary long-form documents, reports, Atrium notes, context objects.
- `stationery_art`: mythic letter, mythic-letter-johannah, one-off art/stationery pieces with image placement, opacity, backgrounds, TikZ, masks, ornaments.
- `physical_sheet_profile`: optional per-object/profile substrate for label/sticker content, not the whole sheet contract.
- `campaign_art`: Elian packet/poster; production-art dependent, placeholder-safe locally.
- `resume`: resume/CV; document-like but structurally distinct enough to remain its own family.

Manifest families classify **assembled render targets**:

- `bundle_longform`: source graph / bundle / composite stack rendered as one long-form PDF work.
- `packet_review`: state/lifecycle projection, not a document profile.
- `physical_sheet`: labels/stickers where grid/position validation is the core contract.
- `campaign_packet`: multi-asset campaign assemblies.

A manifest can request that each child object render under a specific profile or profile family, then assemble the children. Assembly may be individual PDF render + stitching, PDF render + page-number adjustment + stitching, combined Markdown/LaTeX generation, or a hybrid strategy. Keep this as an explicit manifest-family decision, not hidden inside profile resolution.

### 3. Mythic letter is an art/stationery line

`mythic-letter` and `mythic-letter-johannah` should not be forced into the ordinary document-spine abstraction. They need controlled art placement:

- background images
- watermark / opacity
- page overlays
- TikZ / coordinate placement
- header/footer artifact metadata
- masks and ornaments
- optional one-off LaTeX escape hatches

This family should still reuse shared Pandoc compatibility helpers where safe: `tightlist`, longtable when relevant, font setup, image path resolution, evidence, and asset inventory.

### 4. Atrium context-object rendering is a future adapter layer

Recipes, transcripts, convergence logs, Keeper captures, halos, and other Atrium context objects should not automatically become separate rendering engines. Treat them first as source-object adapters feeding the document spine unless their structure earns a named manifest subtype or artifact family.

Expected future adapter responsibilities:

- normalize Atrium frontmatter
- preserve canonical object metadata in evidence
- resolve wiki/Atrium links into readable PDF links or footnotes
- compile source inventories and object provenance
- support object-specific generated sections
- optionally use Pandoc Lua filters / Markdown extensions

Example taxonomy:

```text
Atrium markdown object
  -> AtriumObjectCompiler / frontmatter normalizer
  -> ProjectionPlan(profile_family=document_spine, object_kind=transcript|recipe|halo|keeper_capture|convergence_log)
  -> Pandoc-backed renderer
```

Use named manifest subtypes only when recurrence and validation requirements justify them:

```text
transcript_review.yaml
recipe_card.yaml
halo_packet.yaml
keeper_stack.yaml
convergence_log_digest.yaml
```

### 5. Bundle/manifest assembly contract

Bundle and packet-review behavior should live at the manifest-family layer. A manifest may contain an ordered source graph whose nodes request explicit profiles or profile-family constraints. The compiler should produce per-child `ProjectionPlan`s, invoke the document/profile renderer for each child or fragment, then assemble according to the manifest family's strategy.

Evidence for assembled artifacts must include:

- manifest family/subtype;
- ordered source graph and child object IDs/paths;
- requested profile/profile family per child;
- resolved profile stack per child;
- assembly strategy;
- page/section numbering strategy;
- child render evidence references or embedded summaries;
- final PDF validation.

---

## Task 1: Add resolver tests that capture current failure mode

**Objective:** Prove that `foundry profiles` and `foundry doc` must resolve the same defaults/template/environment for `tech`, `risk`, and `creative`.

**Files:**
- Create: `tests/test_profile_resolver.py`
- Read only: `engine/profile_checker.py`
- Read only: `renderers/pandoc_renderer.py`

**Step 1: Write failing tests**

Create tests that assert:

```python
def test_tech_resolves_yugenbase_and_technology_defaults():
    resolved = resolve_profile("tech")
    assert [p.name for p in resolved.defaults_stack] == ["yugenbase.yaml", "technology.yaml"]
    assert resolved.template_path.name == "base.tex"
    assert resolved.profile_family == "document_spine"


def test_risk_resolves_yugenbase_and_risk_defaults():
    resolved = resolve_profile("risk")
    assert [p.name for p in resolved.defaults_stack] == ["yugenbase.yaml", "risk.yaml"]
    assert resolved.template_path.name == "base.tex"
    assert resolved.profile_family == "document_spine"


def test_resolver_sets_local_import_environment():
    resolved = resolve_profile("tech")
    env = resolved.render_environment
    assert "profiles/40_latex_import/styles/texmf" in str(env.texmfhome)
    assert "profiles/40_latex_import" in ":".join(map(str, env.resource_paths))
    assert resolved.boundary["target_40_latex_mutated"] is False
```

**Step 2: Run RED**

```bash
python3.14 -m pytest tests/test_profile_resolver.py -q
```

Expected: FAIL because `engine.profile_resolver` does not exist.

---

## Task 2: Implement `engine/profile_resolver.py`

**Objective:** Create the single source of truth for profile resolution.

**Files:**
- Create: `engine/profile_resolver.py`
- Test: `tests/test_profile_resolver.py`

**Implementation shape:**

```python
@dataclass(frozen=True)
class RenderEnvironment:
    cwd: Path
    texmfhome: Path
    texinputs: str
    resource_paths: list[Path]


@dataclass(frozen=True)
class ResolvedProfile:
    profile_id: str
    canonical_profile_id: str
    profile_family: str
    defaults_stack: list[Path]
    template_path: Path
    asset_roots: list[Path]
    render_environment: RenderEnvironment
    boundary: dict[str, Any]
    warnings: list[str]
```

Initial canonical mappings:

```python
ALIASES = {
    "tech": "yugen-tech",
    "risk": "yugen-risk",
    "creative": "yugen-creative",
}
```

Initial file mapping can remain explicit, but it must live only here. Later this can be loaded from profile YAML.

**Step 1:** Make the three tests pass with minimal explicit mapping.

**Step 2:** Run:

```bash
python3.14 -m pytest tests/test_profile_resolver.py -q
python3.14 -m pytest -q
```

Expected: all existing tests still pass.

---

## Task 3: Route `PandocRenderer` through the resolver

**Objective:** Ensure actual document/manifest renders use the same facts as profile checks.

**Files:**
- Modify: `renderers/pandoc_renderer.py`
- Test: `tests/test_renderers.py`
- Test: `tests/test_profile_resolver.py`

**Required behavior:**

For a `ProjectionPlan(profile_id="tech")`, `PandocRenderer` command must include:

```text
--defaults .../profiles/40_latex_import/defaults/yugenbase.yaml
--defaults .../profiles/40_latex_import/defaults/technology.yaml
--template .../profiles/40_latex_import/templates/base.tex
```

For `risk`, it must include:

```text
--defaults .../yugenbase.yaml
--defaults .../risk.yaml
--template .../base.tex
```

Renderer evidence must include:

```json
"profile": {
  "profile_id": "tech",
  "canonical_profile_id": "yugen-tech",
  "profile_family": "document_spine"
}
```

and boundary evidence:

```json
"boundary": {
  "target_40_latex_mutated": false,
  "production_output": false,
  "local_import_defaults": true,
  "local_import_templates": true,
  "local_import_styles": true
}
```

**Step 1:** Write tests against the command/evidence assembly. Prefer unit tests that monkeypatch `subprocess.run` only at the renderer boundary.

**Step 2:** Run RED.

**Step 3:** Modify `PandocRenderer` to call `resolve_profile(plan.profile_id)` and remove local duplicate `_find_profile_defaults()` / `_infer_template()` logic or make them thin compatibility wrappers.

**Step 4:** Run GREEN:

```bash
python3.14 -m pytest tests/test_renderers.py tests/test_profile_resolver.py -q
python3.14 -m pytest -q
```

---

## Task 4: Copy local imported assets and stop relying on legacy cwd

**Objective:** Give Optical Foundry its own mutable asset set so renders do not depend on `40_latex/assets` except as explicit read-only fallback.

**Files:**
- Create directory: `profiles/40_latex_import/assets/`
- Modify: `engine/profile_resolver.py`
- Test: `tests/test_profile_resolver.py`
- Docs: `docs/PROFILE_AND_PANDOC_REFERENCE.md`

**Step 1: Copy assets**

Copy from:

```text
~/Digital_Workspace/40_latex/assets/
```

to:

```text
profiles/40_latex_import/assets/
```

Do not mutate `40_latex`.

**Step 2: Resolver expectations**

Resource path should prefer local imports:

```text
.
profiles/40_latex_import/assets
profiles/40_latex_import/templates
<input file directory>
```

Read-only fallback may include `40_latex/assets`, but evidence must say when fallback was used.

**Step 3: Tests**

Add tests that assert required logo paths exist locally:

```python
def test_yugen_logo_assets_are_local_imports():
    resolved = resolve_profile("tech")
    assert any((root / "logo_yugen_navy_wordmark.png").exists() for root in resolved.asset_roots)
```

**Step 4: Run**

```bash
python3.14 -m pytest tests/test_profile_resolver.py -q
python3.14 -m pytest -q
```

---

## Task 5: Create the neutral document-spine profile layer

**Objective:** Split non-brand long-form document behavior from Yugen branding.

**Files:**
- Create: `profiles/40_latex_import/defaults/document_spine.yaml`
- Create or modify: `profiles/40_latex_import/defaults/atrium_report.yaml`
- Keep compatibility: `technology.yaml`, `risk.yaml`, `creative.yaml`, `yugenbase.yaml`
- Modify: `engine/profile_resolver.py`
- Test: `tests/test_profile_resolver.py`

**Design:**

`document_spine.yaml` owns:

- Pandoc input/output extensions.
- PDF engine.
- template default: `base.tex` or future neutralized `document_spine.tex`.
- documentclass/classoption.
- geometry.
- TOC/section behavior.
- longtable / tightlist expectations.
- base fonts / typography variables.
- neutral header/footer slots.

Brand overlays own:

- color palette.
- logo path.
- `division`.
- `tagline`.
- footer email.
- style package, if still used.

**Acceptance:**

- `atrium-report` renders through neutral long-form spine without Yugen branding.
- `tech`, `risk`, `creative` still render through the same spine plus Yugen overlays.
- Current profile IDs remain accepted.

---

## Task 6: Preserve mythic letter as `stationery_art` family

**Objective:** Avoid flattening mythic letter into ordinary long-form document rendering.

**Files:**
- Modify: `engine/profile_resolver.py`
- Test: `tests/test_profile_resolver.py`
- Optional later: `profiles/40_latex_import/defaults/art_stationery_base.yaml`

**Required behavior:**

```python
def test_mythic_letter_johannah_is_stationery_art_family():
    resolved = resolve_profile("mythic-letter-johannah")
    assert resolved.profile_family == "stationery_art"
    assert resolved.template_path.name == "mythic_letter_johannah.tex"
```

Preserve support for:

- `letterhead_image`
- `watermark_image`
- `watermark_opacity`
- `top_left_art`
- `bottom_right_art`
- artifact header/footer metadata
- future TikZ overlays / masks

Do not force TOC/document bundle assumptions onto this family unless explicitly requested by manifest/profile.

---

## Task 7: Add Atrium object adapter skeleton without overbuilding

**Objective:** Reserve the foundation for Atrium frontmatter, links, recipes, transcripts, convergence logs, Keeper captures, and halos without prematurely hardcoding every object type.

**Files:**
- Create: `engine/atrium_object.py`
- Create: `tests/test_atrium_object.py`
- Possibly modify: `renderers/document_renderer.py`

**Initial API:**

```python
@dataclass(frozen=True)
class AtriumObject:
    path: Path
    uid: str | None
    object_kind: str | None
    title: str
    frontmatter: dict[str, Any]
    body: str
    outbound_links: list[str]
```

Initial function:

```python
def load_atrium_object(path: Path) -> AtriumObject:
    ...
```

Start minimal:

- parse YAML frontmatter
- extract `uid`, `kind` or `object_kind`, `title`
- extract wiki-style links and Markdown links
- do not resolve links yet

**Future extension points:**

- link resolver
- frontmatter normalizer
- Pandoc Lua filters
- generated source inventory sections
- object-specific adapters: `recipe`, `transcript`, `halo`, `keeper_capture`, `convergence_log`

---

## Task 8: Add smoke matrix harness for hard legacy inputs

**Objective:** Make the manually run smoke tests reproducible and honest.

**Files:**
- Create: `tests/test_smoke_40_latex_inputs.py` or `scripts/smoke_40_latex_inputs.py`
- Generated output: `generated/smoke_40_latex_input_<date>/`

**Initial matrix:**

Documents:

- `~/Digital_Workspace/40_latex/input/financial_report_dec2025.md`
- `~/Digital_Workspace/40_latex/input/redacted_pentest_report.md`
- `~/Digital_Workspace/40_latex/input/cursor_ai.md`
- `~/Digital_Workspace/40_latex/input/swfl_ground_cover_2026-02-03.md`

Profiles:

- `atrium-report`
- `tech`
- `risk`
- `creative`

Acceptance:

- PDF exists.
- pages > 0.
- evidence JSON exists.
- evidence says local imports used.
- evidence says `target_40_latex_mutated=false`.
- no `40_latex` writes.

Do not include labels/stickers, Elian production profiles, or mythic art profiles in this generic document matrix.

---

## Task 9: Update profile docs and expansion contract

**Objective:** Keep the conceptual model explicit so future profiles do not collapse into one overloaded bucket.

**Files:**
- Modify: `docs/PROFILE_AND_PANDOC_REFERENCE.md`
- Modify: `contracts/EXPANSION.md`
- Possibly modify: `DESIGN.md`

Add sections for:

- profile family taxonomy
- neutral document spine vs Yugen overlays
- stationery/art family
- physical sheet family
- campaign-art placeholder posture
- Atrium object adapter layer
- when a context object should be a profile vs adapter vs manifest subtype

---

## Verification Command Set

Run before considering refactor complete:

```bash
cd ~/Digital_Workspace/42_optical_foundry_greenfield
python3.14 -m pytest -q
python3.14 -m cli profiles --json
python3.14 -m cli doc ~/Digital_Workspace/40_latex/input/financial_report_dec2025.md --profile tech --output generated/refactor_smoke/financial_report_tech
python3.14 -m cli doc ~/Digital_Workspace/40_latex/input/redacted_pentest_report.md --profile risk --output generated/refactor_smoke/redacted_pentest_risk
```

Expected:

- test suite passes.
- profile checker and renderer agree on defaults/template paths.
- smoke PDFs render with real profile defaults/template stack.
- evidence reports local defaults/templates/styles/assets.
- source `40_latex` remains untouched.

---

## Explicit Non-Goals for This Refactor

- Do not wire full bundle rendering beyond existing behavior.
- Do not solve physical sticker/label grid validation here.
- Do not make Elian production-safe; keep placeholder posture honest.
- Do not design every Atrium object subtype now.
- Do not mutate `~/Digital_Workspace/40_latex/`.
- Do not turn every object kind into a separate profile prematurely.

The refactor foundation should make those later lines easier, not pretend they are already solved.

---

## Task 9: Add manifest/profile-family separation hooks

**Objective:** Ensure bundle and packet-review manifests can request per-object profiles/profile families without collapsing assembled artifacts into document profiles.

**Files:**
- Modify or extend: `engine/manifest_compiler.py`
- Modify or extend: `engine/projection_plan.py`
- Tests: add manifest-family tests in `tests/`

**Required behavior:**

- A manifest has `manifest_family` / subtype separate from profile family.
- Child objects may specify `profile_id` or `profile_family`.
- The compiler emits child `ProjectionPlan`s with resolved profiles.
- The manifest evidence records requested/resolved child profiles and the assembly strategy.
- `packet_review` is represented as a manifest family, not as a document profile family.

**Out of scope for this task:** full bundle rendering implementation; this task only establishes the schema/resolver seam so later bundle work lands in the right stratum.
