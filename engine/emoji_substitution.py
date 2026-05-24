"""Render-only emoji image substitution for PDF/LaTeX projections.

Markdown source remains canonical. This preprocessor writes a generated Markdown
copy that replaces a small, explicit set of supported emoji clusters with raw
LaTeX inline image macros backed by vendored assets. It deliberately avoids code
fences and inline code spans.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re

from engine.layout_images import _ensure_header_includes


@dataclass(frozen=True)
class EmojiSubstitutionResult:
    changed: bool
    rewritten_source: Path
    inventory: list[dict[str, Any]] = field(default_factory=list)
    asset_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_REPO_ROOT = Path(__file__).resolve().parents[1]
_NOTO_EMOJI_ROOT = _REPO_ROOT / "profiles" / "40_latex_import" / "assets" / "emoji" / "noto"

_SUPPORTED_EMOJI: dict[str, dict[str, Any]] = {
    "26a0": {
        "emoji": "⚠️",
        "clusters": ("⚠️", "⚠"),
        "asset_family": "noto_emoji",
        "pdf_asset": _NOTO_EMOJI_ROOT / "pdf" / "emoji_u26a0.pdf",
    }
}

_EMOJI_HEADER_INCLUDES = [
    r"\usepackage{graphicx}",
    r"\providecommand{\OFEmoji}[1]{\raisebox{-0.12em}{\includegraphics[height=1em]{#1}}}",
]

_INLINE_CODE_RE = re.compile(r"(`+)(.*?)(\1)")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


def preprocess_emoji_substitutions(source: Path, output_dir: Path, render_id: str) -> EmojiSubstitutionResult:
    """Replace supported emoji clusters with vendored inline image assets.

    The original source is never mutated. If no supported emoji are present
    outside Markdown code spans/fences, the original path is returned.
    """

    if not source.exists():
        return EmojiSubstitutionResult(changed=False, rewritten_source=source)

    text = source.read_text(encoding="utf-8", errors="ignore")
    counts: dict[str, int] = {key: 0 for key in _SUPPORTED_EMOJI}

    rewritten_body = _rewrite_markdown_text(text, counts)
    used = {key: count for key, count in counts.items() if count > 0}
    if not used:
        return EmojiSubstitutionResult(changed=False, rewritten_source=source)

    output_dir.mkdir(parents=True, exist_ok=True)
    rewritten = _ensure_header_includes(rewritten_body, _EMOJI_HEADER_INCLUDES)
    out_path = output_dir / f"{render_id}.emoji_assets.md"
    out_path.write_text(rewritten, encoding="utf-8")

    inventory: list[dict[str, Any]] = []
    asset_paths: list[str] = []
    for key, count in used.items():
        spec = _SUPPORTED_EMOJI[key]
        asset = Path(spec["pdf_asset"])
        inventory.append(
            {
                "kind": "emoji_asset",
                "emoji": str(spec["emoji"]),
                "asset_key": key,
                "asset_family": str(spec["asset_family"]),
                "count": count,
                "host_emoji_fonts_required": False,
            }
        )
        asset_paths.append(str(asset))

    return EmojiSubstitutionResult(
        changed=True,
        rewritten_source=out_path,
        inventory=inventory,
        asset_paths=asset_paths,
    )


def _rewrite_markdown_text(text: str, counts: dict[str, int]) -> str:
    lines = text.splitlines(keepends=True)
    rewritten: list[str] = []
    in_fence = False
    fence_marker = ""

    for line in lines:
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker[:3]
                rewritten.append(line)
                continue
            if marker.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
                rewritten.append(line)
                continue

        if in_fence:
            rewritten.append(line)
        else:
            rewritten.append(_rewrite_inline_text(line, counts))

    return "".join(rewritten)


def _rewrite_inline_text(text: str, counts: dict[str, int]) -> str:
    parts: list[str] = []
    pos = 0
    for match in _INLINE_CODE_RE.finditer(text):
        parts.append(_replace_supported_emoji(text[pos : match.start()], counts))
        parts.append(match.group(0))
        pos = match.end()
    parts.append(_replace_supported_emoji(text[pos:], counts))
    return "".join(parts)


def _replace_supported_emoji(text: str, counts: dict[str, int]) -> str:
    rewritten = text
    for key, spec in _SUPPORTED_EMOJI.items():
        asset = Path(spec["pdf_asset"])
        replacement = _latex_emoji_macro(asset)
        for cluster in spec["clusters"]:
            occurrences = rewritten.count(cluster)
            if occurrences:
                counts[key] += occurrences
                rewritten = rewritten.replace(cluster, replacement)
    return rewritten


def _latex_emoji_macro(asset: Path) -> str:
    return r"\OFEmoji{" + asset.as_posix() + "}"
