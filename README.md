# Optical Foundry — Greenfield Architecture

Pandoc-driven render engine. Profile-first architecture. Explicit split between source documents, bundles, packet review views, projection plans, and rendered artifacts. Bundle assembly, label and sticker pipelines. Greenfield design — no mutation of 40_latex.

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

- **Source document/object**: canonical content, usually one Markdown file.
- **Bundle/manifest**: declarative source selection or source graph.
- **Packet**: stateful work/lifecycle container, not primarily a render type.
- **Projection plan / assembly view**: render-time plan that turns objects, bundles, or packet review state into an artifact.
- **Rendered artifact**: PDF/DOCX/HTML output plus evidence sidecars.

## Folder Map

| Directory | Purpose |
|---|---|
| `profiles/` | Profile registry — YAML declarations organized by output class |
| `templates/` | LaTeX templates (Pandoc `--template`) |
| `styles/` | LaTeX style packages (TEXMFHOME) |
| `assets/` | Fonts, logos, figures |
| `engine/` | Core engine: registry, dispatch, Pandoc, frontmatter |
| `renderers/` | Render classes/adapters: document, bundle, packet review, label, sticker |
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
