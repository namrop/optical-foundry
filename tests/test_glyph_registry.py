"""The glyph registry (keeper ruling 2026-09-01: "The glyphs should grow to support what is needed")."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine import glyph_registry as gr
from engine.emoji_substitution import preprocess_emoji_substitutions

REGISTRY = gr.load_registry()


def _registry(emoji_keys=(), fallback=()):
    return {
        "schema": gr.REGISTRY_SCHEMA,
        "emoji": {key: {"emoji": "", "pdf": f"emoji/noto/pdf/emoji_u{key}.pdf"} for key in emoji_keys},
        "fallback_fonts": [{"family": "OFFallbackCJK", "codepoints": [ord(c) for c in fallback], "faces": {}}]
        if fallback
        else [],
    }


def _lower(text, registry):
    return gr.lower_glyphs(
        text, registry, emoji_macro=lambda k: f"<E:{k}>", fallback_macro=lambda f, run: f"<F:{run}>"
    )


def test_registry_file_is_valid_and_every_asset_exists():
    assert REGISTRY["schema"] == gr.REGISTRY_SCHEMA
    for key, entry in REGISTRY["emoji"].items():
        assert (gr.ASSETS_ROOT / entry["pdf"]).is_file(), key
    for font in REGISTRY["fallback_fonts"]:
        for rel in font["faces"].values():
            assert (gr.ASSETS_ROOT / rel).is_file()
        assert font["characters"] == "".join(chr(cp) for cp in font["codepoints"])


def test_the_keeper_capture_sign_off_glyph_is_registered():
    assert "1f56f" in REGISTRY["emoji"]  # 🕯, the corpus's sign-off glyph (§7, 2026-09-01)


def test_variation_selector_is_optional_and_absorbed():
    reg = _registry(["1f56f"])
    assert _lower("a \U0001F56F\uFE0F b \U0001F56F c", reg).text == "a <E:1f56f> b <E:1f56f> c"


def test_longest_sequence_wins():
    reg = _registry(["1f3f3", "1f3f3_200d_1f308"])
    flag = "\U0001F3F3\uFE0F\u200D\U0001F308"
    assert _lower(f"x{flag}y", reg).text == "x<E:1f3f3_200d_1f308>y"


def test_code_is_left_literal():
    reg = _registry(["1f56f"], fallback="斩")
    text = "p 🕯 斩\n`🕯 斩`\n```\n🕯 斩\n```\n"
    out = _lower(text, reg).text
    assert out == "p <E:1f56f> <F:斩>\n`🕯 斩`\n```\n🕯 斩\n```\n"


def test_fallback_runs_are_wrapped_whole_and_unregistered_cjk_is_reported():
    lowered = _lower("the 斩杀线 line, and 光", _registry(fallback="斩杀线"))
    assert lowered.text == "the <F:斩杀线> line, and 光"
    assert lowered.fallback_counts == {"OFFallbackCJK": 3}
    assert lowered.fallback_missing == ["U+5149"]


def test_scan_skips_covered_characters_and_registered_glyphs(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("© ✓ 🕯 🪐 斩 光 `🧠`\n", encoding="utf-8")
    covered = {ord(c) for c in "© ✓"} | set(range(0x20, 0x7F))
    needs = gr.scan_needed([src], covered=covered, registry=_registry(["1f56f"], fallback="斩"),
                           noto_keys={"1f56f", "1fa90", "1f9e0", "a9"})
    assert set(needs.emoji) == {"1fa90"}
    assert set(needs.fallback) == {0x5149}
    assert needs.unresolved == {}


def test_preprocessor_lowers_registered_emoji_and_fallback(tmp_path):
    src = tmp_path / "s.md"
    src.write_text("---\ntitle: T\n---\n\n# 🕯️ Heading\n\nThe 斩杀线 line.\n", encoding="utf-8")
    result = preprocess_emoji_substitutions(src, tmp_path / "out", "s")
    text = result.rewritten_source.read_text(encoding="utf-8")
    assert "\\OFEmoji{" in text and "emoji_u1f56f.pdf" in text
    assert "\\OFFallbackCJK{斩杀线}" in text
    assert "\\newfontfamily\\OFFallbackCJKFont{OFFallbackCJK-Regular.otf}" in text
    kinds = {entry["kind"] for entry in result.inventory}
    assert kinds == {"emoji_asset", "glyph_fallback_font"}


@pytest.mark.skipif(not (shutil.which("pandoc") and shutil.which("xelatex")), reason="pandoc/xelatex missing")
def test_keeper_render_passes_the_glyph_lint_with_emoji_and_cjk(tmp_path):
    from renderers.document_renderer import DocumentRenderer

    src = tmp_path / "glyphs.md"
    src.write_text(
        "---\ntitle: Glyphs\ntoc: false\nnumbersections: false\n---\n\n"
        "# 🕯️ Sign-off\n\nA kill line, 斩杀线, and a planet 🪐 with a check ✅.\n\n**Bold 斩杀线.**\n",
        encoding="utf-8",
    )
    evidence = DocumentRenderer().render(src, "keeper", output_dir=str(tmp_path / "out"))
    if not isinstance(evidence, dict):
        evidence = json.loads(Path(evidence).read_text())
    assert evidence["status"] == "ok", evidence.get("error")
    pdf = evidence["output"]["pdf_path"]
    text = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True, check=True).stdout
    assert "斩杀线" in text


def test_check_marks_are_symbols_fallback_and_stay_text():
    families = {f["family"]: f for f in REGISTRY["fallback_fonts"]}
    assert {0x2713, 0x2714} <= set(families["OFFallbackSymbols"]["codepoints"])


def test_inline_code_glyphs_the_code_face_lacks_get_a_lua_filter(tmp_path):
    src = tmp_path / "c.md"
    src.write_text("Prose only.\n\n- `🧠 Metacognition` header, and `⚠ warn`.\n", encoding="utf-8")
    result = preprocess_emoji_substitutions(src, tmp_path / "out", "c")
    assert result.lua_filter is not None
    lua = result.lua_filter.read_text(encoding="utf-8")
    assert "emoji_u1f9e0.pdf" in lua
    if gr.monospace_coverage():  # DejaVu Sans Mono has ⚠, so code keeps its own glyph
        assert "emoji_u26a0.pdf" not in lua


@pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc missing")
def test_code_inline_filter_splits_code_around_the_glyph(tmp_path):
    flt = tmp_path / "f.lua"
    flt.write_text(gr.code_inline_lua_filter({"🧠": "\\OFEmoji{x.pdf}"}), encoding="utf-8")
    out = subprocess.run(["pandoc", "-t", "latex", "--lua-filter", str(flt)], input="a `🧠 b` c\n",
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == "a \\OFEmoji{x.pdf}\\texttt{\\ b} c"
