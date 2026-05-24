# Noto Emoji asset subset

This directory contains a deliberately small vendored subset of Noto Emoji assets used by Optical Foundry's render-only emoji substitution path.

## Provenance

- Upstream: <https://github.com/googlefonts/noto-emoji>
- Seed asset: `emoji_u26a0.svg` / warning sign, Unicode U+26A0
- License: SIL Open Font License 1.1, inherited from the upstream Noto Emoji repository.

## Policy

These assets are render projection inputs, not source-canonical content. Markdown sources keep their original Unicode emoji/status glyphs. The renderer may lower supported emoji clusters to these assets for PDF/LaTeX output so that glyph correctness does not depend on host emoji fonts.

Oasis-native replacements can be added one glyph at a time by replacing or overriding the corresponding asset while preserving the explicit registry/evidence surface.
