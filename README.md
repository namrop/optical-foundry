# Optical Foundry — Greenfield Architecture

Pandoc-driven render engine. Profile-first architecture with two stable input classes: Markdown documents and typed render manifests. Manifests can target packets, bundles, label runs, sticker sheets, CAM Stack, Codex 0, or any recurring render case that earns a subtype. Greenfield design — no mutation of 40_latex.

## Quickstart

```bash
# (Not yet implemented — architecture phase)
foundry render input.md --profile risk
foundry render bundle.bundle.yaml --output out.pdf
foundry profiles list
foundry validate profile_id
```

## Architecture

See `DESIGN.md` for the complete architecture design document.

## Conceptual Split

- **Markdown document**: direct Foundry input for one canonical source object.
- **Render manifest**: direct Foundry input for every recurring assembled/projection case.
- **Manifest subtype**: named contract such as `label_run`, `sticker_sheet`, `composite_bundle`, `cam_stack`, `codex_bundle`, or `forge_packet_review`.
- **Bundle**: source graph/content grouping, usually rendered through a manifest.
- **Packet**: work/lifecycle container; rendered only through a packet-review manifest that projects packet state.
- **Projection plan / assembly view**: internal compiled render plan derived from Markdown or a manifest.
- **Rendered artifact**: PDF/DOCX/HTML output plus evidence sidecars.

## Folder Map

| Directory | Purpose |
|---|---|
| `profiles/` | Profile registry — YAML declarations organized by output class |
| `templates/` | LaTeX templates (Pandoc `--template`) |
| `styles/` | LaTeX style packages (TEXMFHOME) |
| `assets/` | Fonts, logos, figures |
| `engine/` | Core engine: registry, dispatch, Pandoc, frontmatter |
| `renderers/` | Render executors and manifest compilers: document, manifest, bundle/composite, packet review, label, sticker |
| `schemas/` | Schema definitions for profiles, manifests, evidence |
| `contracts/` | Expansion and assembly contracts |
| `cli/` | CLI entrypoints |
| `validators/` | Validation tools |
| `fixtures/` | Synthetic test inputs |
| `tests/` | Test suite |
| `generated/` | Render outputs (gitignored) |

## Status

**Phase**: Architecture design (complete)
**Next**: Implementation Phase 0 — Scaffold role surfaces, projection-plan model, and profile registry
