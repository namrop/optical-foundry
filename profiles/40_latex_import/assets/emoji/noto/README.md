# Noto Emoji asset subset

Vendored Noto Emoji images used by Optical Foundry's render-only glyph substitution. The set is listed, with provenance per entry, in `../../glyph_registry.json`; this directory holds the files.

## Provenance

- Upstream: <https://github.com/googlefonts/noto-emoji>. The seed `emoji_u26a0.svg` (warning sign) was vendored 2026-05-24; the rest are from release v2.051 (the nixpkgs `noto-fonts-color-emoji` source), added 2026-09-30.
- License: the upstream README states that the image resources (`svg/`, `png/`) are under the Apache License 2.0 and the fonts under the SIL Open Font License 1.1. These files are images, so Apache-2.0. (This README said OFL until 2026-09-30.)

## Policy

These assets are render projection inputs, not source-canonical content. Markdown sources keep their Unicode emoji. The renderer lowers registered emoji to these assets for PDF/LaTeX output so glyph correctness does not depend on host emoji fonts.

The set grows to cover what the corpus uses (keeper ruling 2026-09-01: "The glyphs should grow to support what is needed"):

    python3 -m cli glyphs scan <sources…> --noto-source <noto-emoji tree>
    python3 -m cli glyphs grow <sources…> --noto-source <noto-emoji tree> --cjk-font <NotoSansCJK-Regular.ttc> --cjk-font-bold <NotoSansCJK-Bold.ttc>

`grow` copies each needed SVG here, converts it to a vector PDF with `rsvg-convert`, and records it in the registry. An emoji is vendored only when a code point in it is missing from the body font, so covered characters (©, ✓, ↔) stay text. CJK and kana go to the subset fallback font in `../../fonts/glyph_fallback/` instead, so they stay text.

Oasis-native replacements can be added one glyph at a time by replacing the corresponding asset while keeping its registry entry.
