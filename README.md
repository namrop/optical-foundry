# Optical Foundry — Greenfield Architecture

Pandoc-driven render engine. Profile-first architecture. Bundle assembly.
Label and sticker pipelines. Greenfield design — no mutation of 40_latex.

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

## Folder Map

| Directory | Purpose |
|---|---|
| `profiles/` | Profile registry — YAML declarations organized by output class |
| `templates/` | LaTeX templates (Pandoc `--template`) |
| `styles/` | LaTeX style packages (TEXMFHOME) |
| `assets/` | Fonts, logos, figures |
| `engine/` | Core engine: registry, dispatch, Pandoc, frontmatter |
| `renderers/` | Render classes: document, packet, label, sticker, bundle |
| `schemas/` | Schema definitions for profiles, manifests, evidence |
| `contracts/` | Expansion and assembly contracts |
| `cli/` | CLI entrypoints |
| `validators/` | Validation tools |
| `fixtures/` | Synthetic test inputs |
| `tests/` | Test suite |
| `generated/` | Render outputs (gitignored) |

## Status

**Phase**: Architecture design (complete)
**Next**: Implementation Phase 0 — Scaffold and profile registry
