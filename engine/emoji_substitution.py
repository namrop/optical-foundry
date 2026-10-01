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

from engine.glyph_registry import (
    ASSETS_ROOT,
    code_inline_lua_filter,
    iter_prose_segments,
    load_registry,
    lower_glyphs,
    monospace_coverage,
)
from engine.layout_images import _ensure_header_includes


@dataclass(frozen=True)
class EmojiSubstitutionResult:
    changed: bool
    rewritten_source: Path
    inventory: list[dict[str, Any]] = field(default_factory=list)
    asset_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    lua_filter: Path | None = None


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

    def emoji_latex(key: str) -> str:
        return _latex_emoji_macro(ASSETS_ROOT / entries[key]["pdf"])

    def fallback_latex(family: str, run: str) -> str:
        return f"\\{family}{{{run}}}"

    lowered = lower_glyphs(text, registry, emoji_macro=emoji_latex, fallback_macro=fallback_latex)
    # Registered glyphs inside inline code spans: lowered by a pandoc Lua filter,
    # since a macro written into a code span would print literally.
    code_spans = "\n".join(
        seg[1:-1] if len(seg) > 1 else seg
        for seg, prose in iter_prose_segments(text)
        if not prose and seg.startswith("`")
    )
    mono = monospace_coverage()
    code_registry = {
        **registry,
        "emoji": {
            key: entry for key, entry in entries.items()
            if not all(int(part, 16) in mono for part in key.split("_"))
        },
        "fallback_fonts": [
            {**font, "codepoints": [cp for cp in font.get("codepoints", []) if int(cp) not in mono]}
            for font in registry["fallback_fonts"]
        ],
    }
    code_lowered = lower_glyphs(code_spans, code_registry, emoji_macro=lambda k: "", fallback_macro=lambda f, r: "")
    warnings = [
        f"no fallback font covers {cp}; grow the glyph registry (cli glyphs grow)"
        for cp in sorted(set(lowered.fallback_missing) | set(code_lowered.fallback_missing))
    ]
    families = set(lowered.fallback_counts) | set(code_lowered.fallback_counts)
    if not (lowered.emoji_counts or families or code_lowered.emoji_counts):
        return EmojiSubstitutionResult(changed=False, rewritten_source=source, warnings=warnings)

    lua_filter = None
    if code_lowered.emoji_counts or code_lowered.fallback_counts:
        replacements: dict[str, str] = {}
        for key in code_lowered.emoji_counts:
            seq = "".join(chr(int(part, 16)) for part in key.split("_"))
            replacements[seq] = emoji_latex(key)
            if len(seq) == 1:
                replacements[seq + "\ufe0f"] = emoji_latex(key)
        for font in code_registry["fallback_fonts"]:
            if font["family"] in code_lowered.fallback_counts:
                for cp in font.get("codepoints", []):
                    replacements[chr(int(cp))] = fallback_latex(font["family"], chr(int(cp)))
        output_dir.mkdir(parents=True, exist_ok=True)
        lua_filter = output_dir / f"{render_id}.glyph_code.lua"
        lua_filter.write_text(code_inline_lua_filter(replacements), encoding="utf-8")
        for key, count in code_lowered.emoji_counts.items():
            lowered.emoji_counts[key] = lowered.emoji_counts.get(key, 0) + count
        for family, count in code_lowered.fallback_counts.items():
            lowered.fallback_counts[family] = lowered.fallback_counts.get(family, 0) + count

    output_dir.mkdir(parents=True, exist_ok=True)
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
        lua_filter=lua_filter,
    )


def _latex_emoji_macro(asset: Path) -> str:
    return r"\OFEmoji{" + asset.as_posix() + "}"
