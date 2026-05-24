"""Tests for render-only emoji asset substitution."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.emoji_substitution import preprocess_emoji_substitutions


def test_preprocess_emoji_substitutions_rewrites_warning_sign_without_mutating_source(tmp_path):
    src = tmp_path / "emoji-source.md"
    original = (
        "---\n"
        "title: Emoji Probe\n"
        "---\n\n"
        "Visible warning ⚠️ and text warning ⚠ stay semantic.\n\n"
        "Inline code stays literal: `⚠️`.\n\n"
        "```\n"
        "fenced ⚠️ stays literal\n"
        "```\n"
    )
    src.write_text(original, encoding="utf-8")

    result = preprocess_emoji_substitutions(src, tmp_path / "out", "emoji-probe")

    assert result.changed is True
    assert result.rewritten_source != src
    assert src.read_text(encoding="utf-8") == original
    rewritten = result.rewritten_source.read_text(encoding="utf-8")
    assert rewritten.count(r"\OFEmoji{") == 2
    assert "Inline code stays literal: `⚠️`." in rewritten
    assert "fenced ⚠️ stays literal" in rewritten
    assert r"\usepackage{graphicx}" in rewritten
    assert r"\providecommand{\OFEmoji}" in rewritten
    assert result.inventory == [
        {
            "kind": "emoji_asset",
            "emoji": "⚠️",
            "asset_key": "26a0",
            "asset_family": "noto_emoji",
            "count": 2,
            "host_emoji_fonts_required": False,
        }
    ]


def test_preprocess_emoji_substitutions_leaves_sources_without_supported_emoji_untouched(tmp_path):
    src = tmp_path / "plain.md"
    src.write_text("No supported emoji here.\n", encoding="utf-8")

    result = preprocess_emoji_substitutions(src, tmp_path / "out", "plain")

    assert result.changed is False
    assert result.rewritten_source == src
    assert result.inventory == []
