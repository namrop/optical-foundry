# Profile Archive Readiness — Foundry-Owned Runtime Imports

Date: 2026-05-16

## Decision posture

The active Optical Foundry dev branch no longer needs the external legacy `40_latex` tree for profile runtime rendering. Every known canonical profile now resolves defaults and templates from Foundry-owned imports under `profiles/40_latex_import/`, and the exhaustive archive-readiness run produced PDFs for every profile without legacy path leakage.

Do not delete provenance outright. Archive `40_latex` as a cold historical/source-provenance tree after the dev branch is merged/promoted and the live Atrium submodule pointer is updated. Runtime must remain pointed only at Foundry-owned imports.

## Bugs found during exhaustive profile testing

1. `codex0` rendered in smoke tests but was missing from `engine.profile_checker.PROFILE_IDS`, so profile inventory under-counted the runtime surface.
   - Fix: add `codex0` to profile checker mappings, template facts, and bundle-ok classification; add a regression test.
2. `elian-packet` and `elian-poster` defaults referenced `fixtures/assets/elian/*`. With the renderer cwd set to the Foundry-owned profile import root, these failed unless repo-relative fixture paths were accidentally visible.
   - Fix: copy synthetic placeholder assets into `profiles/40_latex_import/assets/elian/` and point Elian defaults at `assets/elian/*`.
3. Label-run compilation emitted YAML fenced code blocks from label frontmatter, but `label_sheet.tex` did not define Pandoc highlighting `Shaded` blocks.
   - Fix: render label frontmatter as plain markdown bullet metadata instead of a syntax-highlighted fenced block.

## Exhaustive validation commands

```bash
python3.14 -m cli profiles --json > generated/profile_archive_readiness_20260516/profile_capability_after_exhaustive_fixes.json
python3.14 -m cli smoke profiles --fixture basic --output generated/profile_archive_readiness_20260516/basic_all --proof --proof-dpi 96 --proof-max-pages 3 --proof-columns 3
python3.14 -m cli smoke profiles --fixture illuminated-initial --output generated/profile_archive_readiness_20260516/illuminated_all --proof --proof-dpi 96 --proof-max-pages 3 --proof-columns 3
python3.14 -m cli doc generated/profile_archive_readiness_20260516/fixtures/resume-smoke.md --profile resume --output generated/profile_archive_readiness_20260516/fixed_layout/resume
python3.14 -m cli doc generated/profile_archive_readiness_20260516/fixtures/elian-packet-smoke.md --profile elian-packet --output generated/profile_archive_readiness_20260516/fixed_layout/elian_packet
python3.14 -m cli doc generated/profile_archive_readiness_20260516/fixtures/elian-poster-smoke.md --profile elian-poster --output generated/profile_archive_readiness_20260516/fixed_layout/elian_poster
python3.14 -m cli manifest generated/profile_archive_readiness_20260516/fixtures/label-run-5164.yaml --output generated/profile_archive_readiness_20260516/fixed_layout/labels_5164
python3.14 -m cli manifest generated/profile_archive_readiness_20260516/fixtures/label-run-15264.yaml --output generated/profile_archive_readiness_20260516/fixed_layout/labels_15264
python3.14 -m cli manifest fixtures/manifests/fixture-sticker-sheet-001.sticker-sheet.yaml --output generated/profile_archive_readiness_20260516/fixed_layout/sticker_sheet
python3.14 -m pytest -q
```

## Results

- Profile inventory: 23 canonical profiles.
- Defaults/templates: 23/23 defaults local; 23/23 templates local.
- Legacy fallback counts: defaults_40_latex=0; templates_40_latex=0.
- Basic prose smoke: 17/17 passed.
- Illuminated-initial smoke: 17/17 passed.
- Fixed-layout / non-prose builds: 6/6 passed.
- Aggregate coverage: 23/23 profiles; missing=[].
- Evidence files parsed: 40.
- PDFs produced in this run: 40.
- Visual proof packets produced: 34.
- Full test suite: `224 passed`.

## Boundary checks

- Render failures: 0.
- Retired evidence-key hits in current archive-readiness output: 0.
- Absolute legacy path hits in current archive-readiness output: 0.
- Bad boundary assertions (`target_legacy_profile_tree_mutated` / `reads_legacy_profile_tree` not false): 0.

## Profile coverage

### Document-compatible profiles covered by both basic and illuminated smokes

- `cam`
- `codex0`
- `convergence`
- `creative`
- `generic-report`
- `keeper`
- `letter`
- `life`
- `mythic`
- `mythic-letter`
- `mythic-letter-johannah`
- `prometheus-packet`
- `risk`
- `tech`
- `yugen-brand`
- `yugen-brand-elevated`
- `yugen-civic`

### Fixed-layout / non-prose profiles covered by profile-specific builds

- `elian-packet`
- `elian-poster`
- `labels-avery-15264`
- `labels-avery-5164`
- `resume`
- `sticker-sheet`

## Expected warnings

- `generated/profile_archive_readiness_20260516/fixed_layout/elian_packet/elian-packet-smoke.evidence.json`
  - Synthetic local Optical Foundry placeholder image; not production campaign art.
- `generated/profile_archive_readiness_20260516/fixed_layout/elian_poster/elian-poster-smoke.evidence.json`
  - Synthetic local Optical Foundry placeholder image; not production campaign art.
- `generated/profile_archive_readiness_20260516/fixed_layout/labels_15264/fixture-label-run-15264.evidence.json`
  - Label run currently renders slot-ordered content as a synthetic placeholder document.
  - Physical Avery/grid placement remains content-driven and is not validated by this compiler.
- `generated/profile_archive_readiness_20260516/fixed_layout/labels_5164/fixture-label-run-5164.evidence.json`
  - Label run currently renders slot-ordered content as a synthetic placeholder document.
  - Physical Avery/grid placement remains content-driven and is not validated by this compiler.
- `generated/profile_archive_readiness_20260516/fixed_layout/sticker_sheet/fixture-sticker-sheet-001.evidence.json`
  - Sticker sheet currently renders cell-ordered content as a synthetic placeholder document.
  - Physical sticker grid placement remains content-driven and is not validated by this compiler.

## Archive recommendation

Archive readiness is green for runtime dependency removal: all known profiles build from Foundry-owned imports, no current evidence leaks active legacy paths, and full tests pass. The safe operational sequence is:

1. Commit these exhaustive-readiness fixes.
2. Merge/promote the Optical Foundry dev branch.
3. Update the live Atrium submodule pointer to the promoted commit.
4. Move external `40_latex` to a cold/provenance archive, not a runtime-accessible fallback.
5. Re-run the profile archive-readiness command set from the promoted location before physically removing/moving the old tree.

