"""Two generic-profile compile failures found by the 2026-09-01 keeper-capture proof render.

docs/plans/2026-08-25_codex0_capability_promotion_map.md §7, attempts 1 and 2:

1. A bundle with section dividers and no chapter openers failed on a non-codex0
   profile with ``Undefined control sequence \\CodexPlateRitualBegin``: every
   divider emits the mark, but its fallback definition was written only when a
   source carried a ``chapter_opener``.
2. A document with ``~~strikeout~~`` failed with ``Undefined control sequence
   \\st``: pandoc lowers strikeout to soul's ``\\st``, and the Foundry templates
   have no ``$if(strikeout)$`` block to load it.

Also here, the third 2026-09-30 defect: the codex0 template defaulted three
apparatus images to paths inside the Codex 0 book's own folder. The work now
names them through manifest variables, guarded as render-resource paths.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from engine.manifest_compiler import CompositeBundleCompiler, _guard_manifest_variables
from engine.profile_resolver import resolve_profile
from renderers.pandoc_renderer import PandocRenderer

needs_tex = pytest.mark.skipif(
    not (shutil.which("pandoc") and shutil.which("lualatex") and shutil.which("pdftotext")),
    reason="pandoc/lualatex/pdftotext not available",
)


def _bundle(tmp_path: Path, profile: str, body: str, *, dividers: bool = True) -> dict:
    source = tmp_path / "body.md"
    source.write_text(f"---\nuid: body\ntitle: Body\n---\n\n# Body\n\n{body}\n", encoding="utf-8")
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": f"generic-defects-{profile}",
        "profile": profile,
        "sources": [{"uid": "body", "path": str(source), "role": "primary_anchor", "order": 1}],
        "render": {"include_toc": False, "numbersections": False},
    }
    if dividers:
        manifest["section_dividers"] = [
            {
                "uid": "month-divider",
                "before_source_order": 1,
                "title": "September",
                "force_right_page": False,
                "blank_after": False,
            }
        ]
    return manifest


def test_divider_without_openers_emits_the_ritual_fallbacks(tmp_path):
    plan = CompositeBundleCompiler().compile(_bundle(tmp_path, "keeper", "Text."))
    text = Path(plan.render_source).read_text(encoding="utf-8")
    assert "\\CodexPlateRitualBegin{}" in text
    assert "\\providecommand{\\CodexPlateRitualBegin}{}" in text
    assert text.index("\\providecommand{\\CodexPlateRitualBegin}{}") < text.index("\\CodexPlateRitualBegin{}\n")


def test_bundle_without_dividers_or_openers_stays_free_of_fallbacks(tmp_path):
    plan = CompositeBundleCompiler().compile(_bundle(tmp_path, "keeper", "Text.", dividers=False))
    assert "\\providecommand{\\CodexPlateRitualBegin}" not in Path(plan.render_source).read_text(encoding="utf-8")


@needs_tex
@pytest.mark.parametrize("profile", ["keeper", "generic-report"])
def test_divider_only_bundle_compiles_on_a_generic_profile(tmp_path, profile):
    plan = CompositeBundleCompiler().compile(_bundle(tmp_path, profile, "Body text after the divider."))
    evidence = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"))
    assert evidence["status"] == "ok", evidence.get("error")
    extracted = subprocess.run(
        ["pdftotext", evidence["output"]["pdf_path"], "-"], capture_output=True, text=True, check=True
    ).stdout
    assert "September" in extracted
    assert "[[OFDIV:" not in extracted


@needs_tex
@pytest.mark.parametrize("profile", ["keeper", "generic-report"])
def test_strikeout_renders_on_a_generic_profile(tmp_path, profile):
    plan = CompositeBundleCompiler().compile(
        _bundle(tmp_path, profile, "Kept ~~struck words~~ kept.", dividers=False)
    )
    evidence = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"))
    assert evidence["status"] == "ok", evidence.get("error")
    assert evidence["render_metadata"]["strikeout_support"] is True
    extracted = subprocess.run(
        ["pdftotext", evidence["output"]["pdf_path"], "-"], capture_output=True, text=True, check=True
    ).stdout
    assert "struck words" in " ".join(extracted.split())


def test_strikeout_detection_ignores_code_and_unparsed_tildes(tmp_path):
    defaults = resolve_profile("keeper").defaults_stack
    source = tmp_path / "s.md"
    source.write_text("Plain.\n\n```\n~~in code~~\n```\n\nInline `~~code~~` too.\n", encoding="utf-8")
    assert PandocRenderer._source_contains_strikeout(source, defaults) is False
    source.write_text("Real ~~strike~~ here.\n", encoding="utf-8")
    assert PandocRenderer._source_contains_strikeout(source, defaults) is True
    source.write_text("No tildes at all.\n", encoding="utf-8")
    assert PandocRenderer._source_contains_strikeout(source, defaults) is False


APPARATUS_KEYS = ("codex_blank_leaf_ornament", "codex_compass_field_icon", "codex_folio_chip_asset")


def test_codex0_template_names_no_book_paths():
    template = resolve_profile("codex0").template_path.read_text(encoding="utf-8")
    assert "assets/codex0/v5/apparatus" not in template
    for key in APPARATUS_KEYS:
        assert f"$if({key})$${key}$$endif$" in template


@pytest.mark.parametrize("key", APPARATUS_KEYS)
def test_apparatus_variables_are_allowlisted_and_path_guarded(key):
    accepted, rejected = _guard_manifest_variables({key: "assets/apparatus/knot.png"})
    assert accepted == {key: "assets/apparatus/knot.png"} and rejected == {}
    for unsafe in ("/abs/knot.png", "../knot.png", "assets/knot.png}\\input{x}", "https://x/knot.png", "assets/knot.txt"):
        accepted, rejected = _guard_manifest_variables({key: unsafe})
        assert accepted == {} and key in rejected, unsafe
