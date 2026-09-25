---
uid: 019fc67e-0303-7526-b6b1-9c42c9a7cecb
kind: note
note_role: architecture_note
validation_profile: standard
status: active
created: 2026-08-03T03:15:26-04:00
updated: 2026-08-03T04:36:54-04:00
beam_home: 42_optical_foundry
title: "Optical Foundry — Manifest Resource Roots and Work-Owned Asset Extraction"
tags:
  - optical-foundry
  - architecture
  - resource-roots
  - content-ownership
  - manifests
  - codex0
  - non-regression
  - implemented
  - shadow-migration
summary: "Implemented generic manifest-declared resource_roots and work-owned asset precedence for Optical Foundry. Codex 0 now owns a hash-verified 39-file resource shadow, Build 39 proves manuscript-root winners with profile fallbacks recorded as shadows, and Keeper visual approval on 2026-08-04 authorizes the initial commit while keeping later image revision and fallback deletion as separate work."
related:
  - path: docs/plans/2026-07-27_architecture_direction_profiles_content_runtime_separation.md
    kind: note
    relation: governed_by
  - path: DESIGN.md
    kind: note
    relation: architecture_context
  - path: 21_letters_and_creative/book/codex0_v5/handoffs/codex0_v6_recovered_full_page_plate_payloads_and_intended_seats_2026-08-02.md
    kind: note
    relation: migration_payload
principal: luis
---

# Manifest Resource Roots and Work-Owned Asset Extraction

**Status: initial resource-root implementation accepted for commit after Keeper visual approval on 2026-08-04; fallback deletion remains a separate no-fallback cleanup gate.**

Keeper acceptance, 2026-08-04:

- representative Build 39 title/frontispiece, divider cutout, full-page reveal,
  witness-inline, apparatus, and ordinary rail/text pages were reviewed;
- the approval applies to the generic resource-root plumbing and the manuscript-owned
  shadow migration, not to freezing every current image as final art;
- later image replacement remains allowed and is accepted as a necessary cost of preserving
  the correct ownership boundary now;
- the Foundry profile copies remain intact in this commit. Visual approval authorizes commit,
  not deletion of the compatibility fallback.

Implementation witness, 2026-08-03:

- generic `resource_roots` support is wired through manifest compilation, projection plans,
  Pandoc, raw-LaTeX `\graphicspath`, and render evidence;
- Codex 0 owns a byte-identical 39-file / 329,981,558-byte resource shadow under
  `book/codex0_v5/assets/codex0/v5/` with a machine-readable hash inventory;
- Build 39 (`volumes-2026-08-03f-resource-root-shadow`) completed all three volumes and
  recorded every active migrated reference as a manuscript-root winner with the Foundry
  copy as a lower-precedence shadow;
- the original Foundry payload is intentionally still present. This note does not authorize
  its deletion or any commit before Keeper review.

This design answers the first execution question left open by the architecture-direction
note: how can a work keep its own images while Optical Foundry renders them through an
existing profile, without a repository split and without regressing the existing profile
set?

The immediate proving case is Codex 0. The contract is deliberately not Codex-specific.

---

## 1. Decision

Add an optional top-level `resource_roots` list to document- and bundle-family render
manifests:

```yaml
kind: codex_bundle
schema_version: bundle_manifest_v1
bundle_id: codex0-v5-voli-2026-08-03
profile: codex0
resource_roots:
  - ../../..
sources:
  # ...
```

Each entry names a **read-only directory containing work-owned render resources**. A
relative root is resolved from the render manifest's directory, never from the caller's
current working directory.

Resource references remain ordinary safe relative paths:

```yaml
background_image: assets/codex0/v5/full_page_plates/example.png
print_image: assets/codex0/v5/full_page_plates/example.png
```

The same effective root order must be used by:

1. Pandoc `--resource-path`;
2. injected LaTeX `\\graphicspath`;
3. engine-side image existence and safety checks;
4. render evidence and resource-provenance reporting.

Profile assets remain supported as a lower-precedence compatibility fallback. Old
manifests that do not declare `resource_roots` preserve their current behavior.

### One-sentence boundary

**Manifests declare where a work's resources live; profiles declare renderer-owned style
resources; the runtime resolves both generically and records which physical resource won.**

---

## 2. Why this is the smallest correct seam

The live pipeline already has most of the required machinery:

- `ResolvedProfile.asset_roots` and `RenderEnvironment.resource_paths` carry
  profile-owned lookup roots;
- `ProjectionPlan.source_resource_roots` carries original source directories;
- `PandocRenderer._prepare_layout_image_source()` already passes roots into the LaTeX
  layout-image preprocessor;
- `preprocess_layout_image_blocks()` already emits `\\graphicspath`;
- image-valued manifest fields already reject absolute paths, parent traversal, URLs,
  and LaTeX control tokens.

What is missing is not a new asset system. It is:

1. an explicit **work-owned root** in the manifest contract;
2. manifest-path provenance so relative roots have stable semantics;
3. one shared ordering across renderer paths;
4. evidence that shows which root supplied an asset.

The design therefore adds a narrow input and connects existing resolver surfaces. It does
not introduce a repository manager, package registry, URI scheme, content-addressed
store, or profile-specific engine branch.

---

## 3. Ownership model

### 3.1 Work-owned resources

These live with the work and are declared through `resource_roots`:

- full-page plates;
- witness photographs and vignettes;
- manuscript-specific illustrations;
- edition-specific art;
- work-specific ornament pools;
- other binary or generated media whose meaning belongs to one work.

### 3.2 Profile-owned resources

These remain in profile configuration and resolve through profile roots:

- templates and style files;
- profile-generic logos or marks genuinely shared by every use of that profile;
- generic background, ornament, and support assets that are part of the reusable visual
  system rather than one work's payload;
- profile defaults, filters, and font declarations.

### 3.3 Runtime-owned resources

These are generated or staged for one render:

- rewritten Markdown;
- rendered diagrams and charts;
- temporary images and intermediates;
- final artifacts and evidence sidecars.

They live in the run/output directory and remain highest-precedence because the runtime
must be able to reference the exact artifact it just generated.

---

## 4. Manifest contract

### 4.1 Shape

Both `document_manifest_v1` and `bundle_manifest_v1` gain:

```yaml
resource_roots:
  - path/to/resources
  - another/path
```

Contract:

- optional;
- array of one or more non-empty path strings when present;
- declaration order is significant;
- duplicate normalized roots are removed while preserving first occurrence;
- relative entries resolve against `manifest_path.parent`;
- absolute entries remain accepted for current local workflows, but generated manifests
  should prefer relative roots where the work and manifest share a repository;
- every normalized root must exist and be a directory before rendering;
- roots are read-only inputs;
- roots must be safe for the existing LaTeX `\\graphicspath` emitter.

This is an additive v1 extension. No schema version bump is required because the field is
optional and manifests without it retain prior semantics.

### 4.2 Manifest provenance is required

`ManifestRenderService.render_manifest()` currently loads a path and passes only the
parsed mapping to a compiler. It must also pass the resolved `manifest_path` through the
existing `**kwargs` compiler boundary.

Required rule:

- a relative `resource_roots` entry without `manifest_path` is a validation error;
- direct programmatic compiler callers may use absolute roots or provide
  `manifest_path=` explicitly;
- no root may silently resolve against process CWD.

This prevents API, CLI, worker, and future web-app callers from getting different assets
from the same manifest.

### 4.3 Plan representation

Add a distinct field to `ProjectionPlan`:

```python
manifest_resource_roots: list[Path] = field(default_factory=list)
```

Do **not** fold these paths into `source_resource_roots` at compile time. They have
different origins and need separate evidence:

- `source_resource_roots`: inferred from canonical source locations;
- `manifest_resource_roots`: explicitly declared by the work;
- profile roots: supplied by the selected rendering profile.

A renderer helper may combine them into an effective chain, but the plan should preserve
where each root came from.

---

## 5. Resolution order

For a relative resource reference, the effective lookup order is:

1. **render/run root** — generated and staged artifacts for this invocation;
2. **source roots** — original source directories, in deterministic source order;
3. **manifest resource roots** — explicit work-owned roots, in declaration order;
4. **profile roots** — profile-owned assets and resource paths, in current resolver order.

Rationale:

- run-local generated files must resolve to the artifact created by this run;
- a source-local `image.png` should not be unexpectedly shadowed by a broad work root;
- work-owned resources must win over legacy profile copies during migration;
- profile assets remain a compatibility fallback rather than an ownership sink.

The final chain is normalized and de-duplicated by canonical path while preserving the
first occurrence.

### Collision behavior

When an engine-visible resource reference exists in more than one root:

- the first match wins;
- render evidence records the winning path and all shadowed matches;
- the render emits a collision warning;
- a future strict mode may promote collisions to errors, but the first migration needs
  warnings so a work-owned copy can shadow a legacy profile copy during verification.

A collision must never be silent. The shadow interval is useful only if evidence proves
that the work-owned file, not the old profile copy, supplied the render.

---

## 6. Renderer integration

### 6.1 Shared root-chain helper

Create one generic helper, conceptually:

```python
def effective_resource_roots(
    plan: ProjectionPlan,
    profile: ResolvedProfile,
    run_dir: Path,
) -> list[ResolvedResourceRoot]:
    ...
```

A `ResolvedResourceRoot` evidence record should contain at least:

```json
{
  "path": "/absolute/normalized/path",
  "origin": "run|source|manifest|profile",
  "order": 0
}
```

The runtime may initially keep `Path` lists internally, but evidence must retain origin.
No Codex IDs or book-tree paths belong in this helper.

### 6.2 Pandoc

`PandocRenderer._build_command()` currently builds `--resource-path` from profile render
environment paths. Change it to consume the effective chain.

The command must not use a profile-only root list while LaTeX uses a broader list; that
would make Markdown images and raw LaTeX images resolve differently.

### 6.3 LaTeX

`PandocRenderer._prepare_layout_image_source()` currently supplies:

- local import root;
- profile asset roots;
- source resource roots.

Replace that ad hoc construction with the effective chain, preserving the run/source/work/profile
precedence above. The existing TeX-safe-root checks remain authoritative.

This chain must cover ordinary raw `\\includegraphics` emitted by bundle assembly and Lua
filters, not only fenced `of-image` blocks. The injected `\\graphicspath` is the bridge.

### 6.4 Typed image fields

The existing safe-relative-path checks for fields such as:

- `background_image`;
- `print_image`;
- `titlepage_background_image`;
- `logo_path`;

remain in force. After validation, these references should pass through a generic
resource resolver that records winner and collision evidence.

Arbitrary Markdown images do not need a full AST asset catalog in this phase. Recording
the effective roots in evidence plus resolving typed engine-owned image fields is the
minimum truthful proof surface.

---

## 7. Evidence contract

Every successful render with resource roots records:

```json
{
  "resource_resolution": {
    "effective_roots": [
      {"path": "...", "origin": "run", "order": 0},
      {"path": "...", "origin": "source", "order": 1},
      {"path": "...", "origin": "manifest", "order": 2},
      {"path": "...", "origin": "profile", "order": 3}
    ],
    "resolved_resources": [
      {
        "reference": "assets/codex0/v5/full_page_plates/example.png",
        "winner": "/work/assets/codex0/v5/full_page_plates/example.png",
        "winner_origin": "manifest",
        "shadowed": ["/profile/assets/codex0/v5/full_page_plates/example.png"]
      }
    ],
    "warnings": []
  }
}
```

The exact evidence envelope may follow current renderer conventions. The required facts
are root order, origin, winner, and shadowed alternatives.

For the Codex migration, acceptance requires `winner_origin: manifest` for every active
plate reference before any profile copy is removed.

---

## 8. Codex 0 migration

### 8.1 Preserve the logical namespace first

The near-term move should preserve current logical references:

```text
assets/codex0/v5/full_page_plates/...
assets/codex0/v5/divider_cutout/...
assets/codex0/v5/witness_inline/...
```

Create the matching work-owned namespace under:

```text
21_letters_and_creative/book/codex0_v5/assets/codex0/v5/
```

The repeated `codex0/v5` segment is not claimed as ideal final information architecture.
It is a migration namespace that avoids changing the spine, generated manifests, raw
sources, and profile fallback at the same time. A later work-native path cleanup can be
separately ruled after ownership is corrected.

### 8.2 Current extraction surface

Measured on 2026-08-03, the Foundry subtree
`profiles/40_latex_import/assets/codex0/v5/` contains:

- 39 tracked files;
- 329,981,558 bytes on disk;
- full-page plates;
- witness-inline assets;
- one divider-cutout leaf.

The earlier 2026-07-27 architecture note's 28-file / 194 MB inventory is historical, not
the current extraction count.

### 8.3 Promotion and inventory

Before copying:

1. produce a machine-readable inventory of every source path, byte size, and SHA-256;
2. compare full-page plates against
   `generated_media/recovered_full_page_plates_from_foundry_2026-08-02/`;
3. use the already recovered manuscript-owned file when hashes match;
4. promote any remaining active files from Foundry with explicit provenance rather than
   treating them as newly generated;
5. let the Atrium root Git LFS policy carry PNG payloads; do not inline binaries or bypass
   LFS;
6. keep source and destination copies byte-identical through the shadow interval.

### 8.4 Generator changes

`codex0_v5/tooling/spine_to_bundle_manifest.py` must:

1. emit `resource_roots` in every generated Optical Foundry manifest;
2. compute a relative path from each output manifest's directory to `book_root`;
3. preserve existing relative resource references;
4. replace `_LEAF_ABS`, which currently points into
   `42_optical_foundry/profiles/40_latex_import/assets/codex0/v5/divider_cutout/`, with the
   logical `DIVIDER_CUTOUT_LEAF_RESOURCE` reference so the generated cut-leaf verso also
   resolves through the manifest root;
5. test manifests written at more than one output depth so root calculation cannot be
   accidentally hard-coded to today's `manifests/generated/volumes-*` layout.

The generated manifest may contain:

```yaml
resource_roots:
  - ../../..
```

when that is the correct path from the emitted manifest to `codex0_v5`; the generator,
not a human constant, computes it.

### 8.5 Shadow verification

Keep Foundry copies during the first proof render, but put manifest roots ahead of profile
roots. Acceptance gates:

1. every active plate resolves from `codex0_v5/assets/...` in evidence;
2. collisions list the Foundry copy as shadowed during the overlap;
3. a bounded Codex render passes with the profile copies temporarily hidden or moved out
   of lookup scope;
4. representative pages containing the divider cutout, full-page reveals, title/frontispiece
   plates, and witness-inline images are visually compared at 100% scale;
5. page geometry, plate aspect ratio, and plate content are unchanged;
6. the complete Foundry unit suite and profile smoke matrix remain green.

Partial-volume renders are valid proof runs when they intentionally exercise the changed
surfaces; completion of all three volumes is not required merely to prove root resolution.

### 8.6 Removal

Only after the no-fallback proof:

1. delete `profiles/40_latex_import/assets/codex0/v5/` from Foundry;
2. regenerate manifests;
3. render the same bounded proof again;
4. verify no evidence path points into the deleted Foundry subtree;
5. run profile contracts and smoke renders again;
6. update historical Codex handoffs that still state the profile subtree is the live
   asset location, preserving their original claim as historical context where needed.

---

## 9. Non-regression matrix

### 9.1 Unit and contract tests

Add tests for:

- absent `resource_roots` preserves prior plan and command behavior;
- absolute manifest root accepted;
- relative manifest root resolves from manifest directory;
- relative root without manifest provenance fails;
- missing path, file-not-directory, empty string, URL, and TeX-unsafe root fail;
- duplicates de-duplicate stably;
- source root precedes manifest root;
- manifest root precedes profile root;
- identical logical resource in work and profile roots selects work and records collision;
- Pandoc `--resource-path` and LaTeX `\\graphicspath` have the same semantic order;
- document, generic bundle, CAM stack, and Codex bundle compilers carry roots without
  subtype-specific branches;
- direct plain-Markdown rendering remains unchanged;
- label, sticker-sheet, and packet-review compilers remain unchanged unless they opt into
  the generic field later.

Likely test homes:

- `tests/test_manifest_compiler.py` or a focused `tests/test_manifest_resource_roots.py`;
- `tests/test_layout_images_preprocessor.py`;
- `tests/test_pandoc_renderer.py`;
- `tests/test_projection_plan.py`;
- Codex generator tests under `codex0_v5/tooling/tests/test_spine_to_bundle_manifest.py`.

### 9.2 Static profile checks

Run:

```bash
python3 -m cli profiles
```

All profile contracts must remain valid.

### 9.3 Render smoke matrix

Run the Foundry profile smoke command before and after the change:

```bash
python3 -m cli smoke profiles --fixture basic --output generated/profile_smoke_resource_roots
```

At minimum preserve the command's default document profile matrix. Add explicit profile
arguments only if the defaults do not cover the current reference families.

The canonical acceptance run belongs on a renderer with the profile-declared fonts
installed. On a host that is not fully provisioned, capture the pre-change failure set
and require a differential non-regression result: no new failed profile, and no existing
failure may change from a provisioning error into a resource-resolution error. Do not
describe an infrastructure-limited matrix as green.

**Design-session baseline, 2026-08-03:** static profile inspection found all 25 profiles'
defaults and templates; the focused manifest/resolver/profile test surface passed 140
tests. The default render matrix passed 2 of 17 profiles (`codex0` and
`mythic-letter-johannah`) and failed 15 of 17 because profile fonts such as Helvetica
were unavailable to XeTeX/fontspec on this host. No runtime code had been changed for
this baseline.

### 9.4 Codex proof set

The bounded proof set must include at least:

- shared beam-cut divider recto;
- generated cut-leaf verso using the former `_LEAF_ABS` path;
- one full-page reveal;
- title/frontispiece image if active;
- one witness-inline image;
- one ordinary text page with rail/ornament composition.

This proves both manifest-typed references and raw LaTeX/image-filter references.

---

## 10. Rollout sequence

### Phase A — Runtime seam

1. add schemas and documentation;
2. preserve manifest path through the service/compiler boundary;
3. add `manifest_resource_roots` to `ProjectionPlan`;
4. implement root normalization and origin evidence;
5. use the effective chain in Pandoc and LaTeX;
6. add collision warnings and tests;
7. run full Foundry tests and profile smoke matrix.

No Codex binary moves occur in this phase.

### Phase B — Codex shadow migration

1. inventory and promote 39 work-owned files under the Codex tree;
2. update the spine generator to emit roots and remove `_LEAF_ABS`;
3. regenerate a bounded manifest;
4. render with both copies present;
5. prove manifest-root winners and byte-equivalent assets;
6. render again with profile fallback hidden.

### Phase C — Extraction

1. remove the Foundry copies;
2. rerun bounded Codex and cross-profile validation;
3. update live ownership documentation;
4. commit Foundry and Atrium/Codex changes in coordinated, independently reviewable
   commits.

### Phase D — Later generalization, not blocking extraction

Defer until after the plate move:

- asset catalogs or stable asset IDs;
- content-addressed storage;
- a `work://` URI scheme;
- profile repository split;
- external profile discovery and installation;
- converting the large `codex0_composition.lua` asset table into a generated work-owned
  catalog;
- eliminating all absolute paths under the older `book/codex0/` ornament tree;
- renaming the migration namespace from `assets/codex0/v5/...` to a cleaner work-local
  layout.

The Lua catalog is real coupling, but its active assets already live outside Foundry. It
should be solved by the same resource-root boundary later, not used to expand the first
implementation into a catalog redesign.

---

## 11. Rejected alternatives

### Put symlinks or mounts inside the profile

Rejected. It preserves the false ownership model, makes deployment depend on workspace
layout, and is difficult to represent honestly in render evidence.

### Infer a content root from the common ancestor of source files

Rejected. Multi-source bundles, generated sources, external sources, and temporary files
make the result implicit and unstable. A work root is an authored render input and should
be declared.

### Use only absolute image paths in manifests and generated Markdown

Rejected. It bypasses the renderer contract, prevents repository movement, and leaves
profile filters and Markdown image handling on different resolution paths.

### Add Codex-specific paths to `profile_resolver.py`

Rejected. It inverts ownership and violates the requirement that the engine know nothing
about which book it renders.

### Build an asset registry before moving anything

Rejected for the near term. IDs, manifests, licensing metadata, hashes, variants, and
package distribution may eventually be useful, but the present defect is a missing lookup
root, not a missing digital-asset-management system.

### Rename `source_resource_roots` and refactor every caller now

Rejected. Keep the source-root concept stable and add the manifest-root concept beside it.
A future consolidation can happen after behavior and evidence are locked.

---

## 12. Rollback

The rollout is deliberately reversible:

- Phase A is additive; removing `resource_roots` from a manifest restores the old path.
- Phase B retains profile copies while evidence proves work-root precedence.
- If a proof render fails, revert the manifest declaration and generator change; no
  profile payload has been deleted.
- Phase C begins only after a successful no-fallback render. If a later regression appears,
  restoring the byte-identical profile subtree is a bounded compatibility rollback while
  the resolver defect is diagnosed.

Rollback does not mean allowing two permanent authorities. The shadow interval is a
migration mechanism with an explicit removal gate.

---

## 13. Acceptance criteria

The design is successfully implemented when all of the following are true:

1. a generic manifest can declare one or more work-owned resource roots;
2. relative roots resolve from manifest location independent of caller CWD;
3. Pandoc and LaTeX use the same semantic root order;
4. source-local assets beat broad work roots; work roots beat profile fallbacks;
5. render evidence identifies root origins, winners, and collisions;
6. old manifests and direct document renders remain behaviorally unchanged;
7. all existing profile contracts and smoke profiles pass;
8. a Codex proof render resolves every active migrated plate from the Codex tree with the
   Foundry subtree hidden;
9. the Foundry Codex asset subtree can be deleted without changing rendered plate content
   or geometry;
10. no Codex-specific path is added to core resolver code.

---

## 14. Recommended implementation packet

The first implementation packet should include only:

- schema and docs extension;
- manifest-path propagation;
- plan field and normalized root-chain helper;
- Pandoc/LaTeX integration;
- evidence and collision reporting;
- focused unit tests;
- one generic fixture proving work-over-profile precedence.

The Codex binary promotion and generator migration should be the second packet. Keeping
those packets separate makes it possible to review the generic resolver before placing
330 MB of real content behind it.
