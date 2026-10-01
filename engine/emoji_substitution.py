"""Render-only glyph substitution for PDF/LaTeX projections.

Markdown source remains canonical. This preprocessor writes a generated Markdown
copy that replaces the emoji in the glyph registry (engine/glyph_registry.py)
with raw LaTeX inline image macros backed by vendored assets, and sets runs of
registered fallback-font characters (CJK, kana) in their vendored font. It
deliberately avoids code fences and inline code spans.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.glyph_registry import ASSETS_ROOT, load_registry, lower_glyphs
from engine.layout_images import _ensure_header_includes


@dataclass(frozen=True)
class EmojiSubstitutionResult:
    changed: bool
    rewritten_source: Path
    inventory: list[dict[str, Any]] = field(default_factory=list)
    asset_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_EMOJI_HEADER_INCLUDES = [
    r"\usepackage{graphicx}",
    r"\providecommand{\OFEmoji}[1]{\raisebox{-0.12em}{\includegraphics[height=1em]{#1}}}",
]


def _fallback_header_includes(registry: dict[str, Any], families: set[str]) -> list[str]:
    lines = [r"\usepackage{fontspec}"]
    for font in registry["fallback_fonts"]:
        family = font["family"]
        if family not in families:
            continue
        faces = font["faces"]
        regular = ASSETS_ROOT / faces["Regular"]
        options = [f"Path={regular.parent.as_posix()}/"]
        if "Bold" in faces:
            options.append(f"BoldFont={Path(faces['Bold']).name}")
        lines.append(
            f"\\newfontfamily\\{family}Font{{{regular.name}}}[{','.join(options)}]"
        )
        lines.append(f"\\providecommand{{\\{family}}}[1]{{{{\\{family}Font #1}}}}")
    return lines


def _pdfstring_include(families: set[str]) -> str:
    # Headings carry these into PDF bookmarks: an emoji contributes nothing there,
    # a fallback run contributes its characters.
    defs = "\\def\\OFEmoji#1{}" + "".join(f"\\def\\{family}#1{{#1}}" for family in sorted(families))
    return (
        "\\AtBeginDocument{\\ifdefined\\pdfstringdefDisableCommands"
        f"\\pdfstringdefDisableCommands{{{defs}}}\\fi}}"
    )


def preprocess_emoji_substitutions(source: Path, output_dir: Path, render_id: str) -> EmojiSubstitutionResult:
    """Lower registered glyphs: emoji to vendored inline images, fallback runs to their font.

    The registry is ``profiles/40_latex_import/assets/glyph_registry.json``
    (``engine/glyph_registry.py``). The original source is never mutated. If no
    registered glyph occurs outside Markdown code spans/fences, the original path
    is returned.
    """

    if not source.exists():
        return EmojiSubstitutionResult(changed=False, rewritten_source=source)

    registry = load_registry()
    text = source.read_text(encoding="utf-8", errors="ignore")
    entries = registry["emoji"]
    lowered = lower_glyphs(
        text,
        registry,
        emoji_macro=lambda key: _latex_emoji_macro(ASSETS_ROOT / entries[key]["pdf"]),
        fallback_macro=lambda family, run: f"\\{family}{{{run}}}",
    )
    warnings = [
        f"no fallback font covers {cp}; grow the glyph registry (cli glyphs grow)"
        for cp in lowered.fallback_missing
    ]
    if not lowered.emoji_counts and not lowered.fallback_counts:
        return EmojiSubstitutionResult(changed=False, rewritten_source=source, warnings=warnings)

    output_dir.mkdir(parents=True, exist_ok=True)
    families = set(lowered.fallback_counts)
    includes = list(_EMOJI_HEADER_INCLUDES)
    if families:
        includes += _fallback_header_includes(registry, families)
    includes.append(_pdfstring_include(families))
    rewritten = _ensure_header_includes(lowered.text, includes)
    out_path = output_dir / f"{render_id}.emoji_assets.md"
    out_path.write_text(rewritten, encoding="utf-8")

    inventory: list[dict[str, Any]] = []
    asset_paths: list[str] = []
    for key, count in lowered.emoji_counts.items():
        entry = entries[key]
        inventory.append(
            {
                "kind": "emoji_asset",
                "emoji": str(entry["emoji"]),
                "asset_key": key,
                "asset_family": "noto_emoji",
                "count": count,
                "host_emoji_fonts_required": False,
            }
        )
        asset_paths.append(str(ASSETS_ROOT / entry["pdf"]))
    for font in registry["fallback_fonts"]:
        family = font["family"]
        if family in lowered.fallback_counts:
            inventory.append(
                {
                    "kind": "glyph_fallback_font",
                    "family": family,
                    "characters": lowered.fallback_counts[family],
                    "faces": {face: str(ASSETS_ROOT / rel) for face, rel in font["faces"].items()},
                    "source": font.get("source", ""),
                }
            )
            asset_paths.extend(str(ASSETS_ROOT / rel) for rel in font["faces"].values())

    return EmojiSubstitutionResult(
        changed=True,
        rewritten_source=out_path,
        inventory=inventory,
        asset_paths=asset_paths,
        warnings=warnings,
    )


def _latex_emoji_macro(asset: Path) -> str:
    return r"\OFEmoji{" + asset.as_posix() + "}"
