"""Tests for Codex 0 inline edition variant preprocessing."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.codex_editions import (  # noqa: E402
    CodexEditionRenderError,
    _normalize_thematic_breaks,
    _strip_editorial_callouts,
    edition_from_source_frontmatter,
    preprocess_codex_edition_blocks,
)
from engine.profile_resolver import resolve_profile  # noqa: E402
from engine.projection_plan import ProjectionPlan  # noqa: E402
from renderers.pandoc_renderer import PandocRenderer  # noqa: E402


def test_codex_edition_preprocessor_selects_tagged_override_over_base(tmp_path):
    src = tmp_path / "variant.md"
    src.write_text(
        "---\n"
        "title: Variant Test\n"
        "codex_edition: reader\n"
        "---\n\n"
        "Before.\n\n"
        "<!-- cx0:variant id=\"how-you-arrived-010\" -->\n"
        "Archival prose with **Markdown**.\n"
        "<!-- cx0:edition reader -->\n"
        "Reader prose with *Markdown*.\n"
        "<!-- cx0:endvariant -->\n\n"
        "After.\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "variant", "reader")
    rewritten = result.rewritten_source.read_text()

    assert result.changed is True
    assert result.edition == "reader"
    assert result.variant_count == 1
    assert result.selected_count == 1
    assert result.fallback_count == 0
    assert result.selected_variant_ids == ["how-you-arrived-010"]
    assert "Reader prose with *Markdown*." in rewritten
    assert "Archival prose" not in rewritten
    assert "cx0:" not in rewritten


def test_codex_edition_preprocessor_inherits_archival_base_when_untagged(tmp_path):
    src = tmp_path / "base.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "Archival base prose.\n"
        "<!-- cx0:edition reader -->\n"
        "Reader prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "base", "archival")
    rewritten = result.rewritten_source.read_text()

    assert "Archival base prose." in rewritten
    assert "Reader prose." not in rewritten
    assert result.fallback_count == 1
    assert result.fallback_variant_ids == ["v1"]


def test_codex_edition_preprocessor_addition_is_empty_for_untagged_edition(tmp_path):
    src = tmp_path / "addition.md"
    src.write_text(
        "Before.\n\n"
        "<!-- cx0:variant id=\"v1\" -->\n"
        "<!-- cx0:edition johannah -->\n"
        "Johannah-only addition.\n"
        "<!-- cx0:endvariant -->\n\n"
        "After.\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "addition", "reader")
    rewritten = result.rewritten_source.read_text()

    assert "Johannah-only addition." not in rewritten
    assert "Before." in rewritten
    assert "After." in rewritten
    assert "cx0:" not in rewritten


def test_codex_edition_preprocessor_addition_present_for_tagged_edition(tmp_path):
    src = tmp_path / "addition2.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "<!-- cx0:edition johannah -->\n"
        "Johannah-only addition.\n"
        "<!-- cx0:endvariant -->\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "addition2", "johannah")
    rewritten = result.rewritten_source.read_text()

    assert "Johannah-only addition." in rewritten


def test_codex_edition_preprocessor_multi_tag_override(tmp_path):
    src = tmp_path / "multi.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "Raw base.\n"
        "<!-- cx0:edition witness,reader -->\n"
        "Veiled prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    for edition in ("witness", "reader"):
        result = preprocess_codex_edition_blocks(src, tmp_path, f"multi-{edition}", edition)
        rewritten = result.rewritten_source.read_text()
        assert "Veiled prose." in rewritten
        assert "Raw base." not in rewritten

    archival = preprocess_codex_edition_blocks(src, tmp_path, "multi-archival", "archival")
    assert "Raw base." in archival.rewritten_source.read_text()


def test_codex_edition_preprocessor_wraps_selected_register_branch(tmp_path):
    src = tmp_path / "register.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "Raw base.\n"
        "<!-- cx0:edition johannah,witness,reader register=\"pataphorical\" -->\n"
        "Fable-register prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "register", "johannah")
    rewritten = result.rewritten_source.read_text()

    assert "Raw base." not in rewritten
    assert "::: {.codex-pataphorical register=\"pataphorical\"}" in rewritten
    assert "Fable-register prose." in rewritten
    assert "cx0:" not in rewritten

    archival = preprocess_codex_edition_blocks(src, tmp_path, "register-archival", "archival")
    archival_text = archival.rewritten_source.read_text()
    assert "Raw base." in archival_text
    assert "codex-pataphorical" not in archival_text


def test_codex_edition_preprocessor_rejects_unsafe_register(tmp_path):
    src = tmp_path / "unsafe-register.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "Raw base.\n"
        "<!-- cx0:edition reader register=\"../pataphorical\" -->\n"
        "Reader prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    with pytest.raises(CodexEditionRenderError, match="unsafe register"):
        preprocess_codex_edition_blocks(src, tmp_path, "unsafe-register", "reader")


def test_codex_edition_preprocessor_supports_xml_style_close(tmp_path):
    src = tmp_path / "xmlclose.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "Raw base.\n"
        "<!-- cx0:edition reader -->\n"
        "Reader prose.\n"
        "<!-- /cx0:variant -->\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "xmlclose", "reader")
    rewritten = result.rewritten_source.read_text()

    assert "Reader prose." in rewritten
    assert "cx0:" not in rewritten


def test_codex_edition_preprocessor_deprecates_fallback_attr(tmp_path):
    src = tmp_path / "deprecated.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" fallback=\"johannah\" -->\n"
        "Raw base.\n"
        "<!-- cx0:edition reader -->\n"
        "Reader prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "deprecated", "archival")
    rewritten = result.rewritten_source.read_text()

    assert "Raw base." in rewritten
    assert any("deprecated" in w for w in result.warnings)


def test_codex_edition_preprocessor_guard_fails_when_edition_inherits_base(tmp_path):
    src = tmp_path / "guard.md"
    src.write_text(
        "<!-- cx0:variant id=\"the-reckoning\" guard=\"witness,reader\" -->\n"
        "Raw archival prose.\n"
        "<!-- cx0:edition witness -->\n"
        "Veiled witness prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    with pytest.raises(CodexEditionRenderError, match="guards edition 'reader'"):
        preprocess_codex_edition_blocks(src, tmp_path, "guard-reader", "reader")


def test_codex_edition_preprocessor_guard_allows_override_and_base(tmp_path):
    src = tmp_path / "guard-ok.md"
    src.write_text(
        "<!-- cx0:variant id=\"the-reckoning\" guard=\"witness,reader\" -->\n"
        "Raw archival prose.\n"
        "<!-- cx0:edition witness -->\n"
        "Veiled witness prose.\n"
        "<!-- cx0:edition reader -->\n"
        "Most veiled reader prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    witness = preprocess_codex_edition_blocks(src, tmp_path, "guard-witness", "witness")
    assert "Veiled witness prose." in witness.rewritten_source.read_text()

    archival = preprocess_codex_edition_blocks(src, tmp_path, "guard-archival", "archival")
    assert "Raw archival prose." in archival.rewritten_source.read_text()


def test_codex_edition_preprocessor_fails_if_markers_present_without_render_edition(tmp_path):
    src = tmp_path / "no-render-edition.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "<!-- cx0:edition johannah -->\n"
        "Private prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    with pytest.raises(CodexEditionRenderError, match="no codex_edition"):
        preprocess_codex_edition_blocks(src, tmp_path, "no-render-edition", "")


def test_codex_edition_preprocessor_strips_editorial_callouts_after_selection(tmp_path):
    src = tmp_path / "callouts.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "<!-- cx0:edition reader -->\n"
        "Reader prose.\n\n"
        "> [!lux-edit]\n"
        "> Remove this from reader-facing renders.\n\n"
        "Still reader prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    result = preprocess_codex_edition_blocks(
        src,
        tmp_path,
        "callouts",
        "reader",
        strip_editorial_callouts=True,
    )
    rewritten = result.rewritten_source.read_text()

    assert "Reader prose." in rewritten
    assert "Still reader prose." in rewritten
    assert "lux-edit" not in rewritten
    assert result.editorial_callouts_stripped == 1


def test_codex_edition_preprocessor_formats_editorial_callouts_when_not_stripping(tmp_path):
    src = tmp_path / "visible-callouts.md"
    src.write_text(
        "Prose before.\n\n"
        "> [!note] Revision lane\n"
        "> This is for Lux, not reader prose.\n"
        ">\n"
        "> Preserve **Markdown** inside the note.\n\n"
        "Prose after.\n"
    )

    result = preprocess_codex_edition_blocks(
        src,
        tmp_path,
        "visible-callouts",
        "",
        format_editorial_callouts=True,
    )
    rewritten = result.rewritten_source.read_text()

    assert result.changed is True
    assert result.editorial_callouts_formatted == 1
    assert "> [!note]" not in rewritten
    assert '::: {.codex-editorial-note kind="note" title="Revision lane"}' in rewritten
    assert "This is for Lux" in rewritten
    assert "Preserve **Markdown**" in rewritten
    assert "Prose after." in rewritten


def test_codex_edition_frontmatter_reads_top_level_and_variables(tmp_path):
    src = tmp_path / "frontmatter.md"
    src.write_text(
        "---\n"
        "variables:\n"
        "  codex_edition: family\n"
        "  codex_strip_editorial_callouts: true\n"
        "---\n\n"
        "Body.\n"
    )

    assert edition_from_source_frontmatter(src) == ("family", True)


def test_pandoc_renderer_codex_prepass_runs_before_layout_images(tmp_path):
    src = tmp_path / "image-variant.md"
    src.write_text(
        "---\n"
        "codex_edition: reader\n"
        "---\n\n"
        "<!-- cx0:variant id=\"v1\" -->\n"
        "<!-- cx0:edition johannah -->\n"
        "```of-image\n"
        "path: assets/private.png\n"
        "placement: inline\n"
        "```\n"
        "<!-- cx0:edition reader -->\n"
        "Reader-only prose.\n"
        "<!-- cx0:endvariant -->\n"
    )
    plan = ProjectionPlan(profile_id="codex0", render_id="image-variant", render_source=src)

    prepared = PandocRenderer()._prepare_codex_edition_source(plan, tmp_path, resolve_profile("codex0"))
    rewritten = prepared.render_source.read_text()

    assert "Reader-only prose." in rewritten
    assert "private.png" not in rewritten
    assert "```of-image" not in rewritten
    assert prepared.boundary_assertions["codex_edition"] == "reader"


def test_pandoc_renderer_codex_prepass_formats_visible_editorial_callouts(tmp_path):
    src = tmp_path / "draft-callout.md"
    src.write_text(
        "Draft prose.\n\n"
        "> [!note] Lux note\n"
        "> Move this later.\n"
    )
    plan = ProjectionPlan(profile_id="codex0", render_id="draft-callout", render_source=src)

    prepared = PandocRenderer()._prepare_codex_edition_source(plan, tmp_path, resolve_profile("codex0"))
    rewritten = prepared.render_source.read_text()

    assert '::: {.codex-editorial-note kind="note" title="Lux note"}' in rewritten
    assert "> [!note]" not in rewritten
    assert prepared.boundary_assertions["codex_editorial_callouts_formatted"] == 1
    assert prepared.boundary_assertions["codex_editorial_callouts_stripped"] == 0


def test_pandoc_renderer_fails_closed_for_cx0_markers_under_non_codex_profile(tmp_path):
    src = tmp_path / "wrong-profile.md"
    src.write_text(
        "---\n"
        "codex_edition: reader\n"
        "---\n\n"
        "<!-- cx0:variant id=\"v1\" -->\n"
        "<!-- cx0:edition reader -->\n"
        "Reader prose.\n"
        "<!-- cx0:endvariant -->\n"
    )
    plan = ProjectionPlan(profile_id="keeper", render_id="wrong-profile", render_source=src)

    with pytest.raises(CodexEditionRenderError, match="require profile codex0"):
        PandocRenderer()._prepare_codex_edition_source(plan, tmp_path, resolve_profile("keeper"))


def test_pandoc_renderer_leaves_other_profiles_with_plain_callouts_unchanged(tmp_path):
    src = tmp_path / "ordinary-callout.md"
    src.write_text("---\ntitle: Ordinary\n---\n\n> [!note] Plain Obsidian note.\n")
    plan = ProjectionPlan(profile_id="keeper", render_id="ordinary-callout", render_source=src)

    prepared = PandocRenderer()._prepare_codex_edition_source(plan, tmp_path, resolve_profile("keeper"))

    assert prepared.render_source == src
    assert prepared.boundary_assertions == {}


def test_pandoc_renderer_leaves_other_renders_without_markers_unchanged(tmp_path):
    src = tmp_path / "ordinary.md"
    src.write_text("---\ntitle: Ordinary\n---\n\nPlain prose.\n")
    plan = ProjectionPlan(profile_id="keeper", render_id="ordinary", render_source=src)

    prepared = PandocRenderer()._prepare_codex_edition_source(plan, tmp_path, resolve_profile("keeper"))

    assert prepared.render_source == src
    assert prepared.boundary_assertions == {}


def test_normalize_thematic_breaks_rewrites_dashes_to_stars():
    """Standalone `---` lines become `* * *` so Pandoc's yaml_metadata_block
    extension does not mistake them for the start of a YAML metadata block.
    """
    text = "Some prose.\n\n---\n\nMore prose.\n"
    result = _normalize_thematic_breaks(text)
    assert "---" not in result
    assert "* * *" in result


def test_normalize_thematic_breaks_preserves_leading_frontmatter():
    """The top-level YAML frontmatter block must not be rewritten — its opening
    `---` and closing `---` are metadata sentinels, not thematic breaks.
    """
    text = "---\ntitle: Test\ncodex_edition: johannah\n---\n\nBody prose.\n\n---\n\nAfter thematic break.\n"
    result = _normalize_thematic_breaks(text)
    assert result.startswith("---\ntitle: Test")
    assert "\n---\n\nBody prose." in result  # frontmatter close preserved
    assert "* * *" in result  # body thematic break normalized
    assert result.count("---") == 2  # only the frontmatter delimiters remain


def test_normalize_thematic_breaks_leaves_fenced_code_alone():
    """A `---` inside a fenced code block is code content, not a thematic break."""
    text = "Before.\n\n```\n---\nyaml: sample\n---\n```\n\n---\n\nAfter.\n"
    result = _normalize_thematic_breaks(text)
    # The `---` inside the code fence stays; the `---` outside becomes `* * *`.
    assert "---\nyaml: sample\n---" in result
    assert "* * *" in result


def test_strip_editorial_callouts_normalizes_adjacent_thematic_breaks(tmp_path):
    """The concrete regression this guards: an editorial callout adjacent to a
    `---` thematic break, when stripped, would leave a bare `---` that Pandoc
    parsed as the start of a YAML metadata block and failed rendering. The
    stripper now normalizes such `---` to `* * *`.
    """
    text = (
        "Opening paragraph.\n\n"
        "> [!note] LER: an editorial correction here.\n"
        "> Continues in blockquote.\n\n"
        "---\n\n"
        "**Following section** with prose.\n"
    )
    stripped, count = _strip_editorial_callouts(text)
    assert count == 1
    assert "LER:" not in stripped
    assert "---" not in stripped  # thematic break normalized away
    assert "* * *" in stripped
    assert "**Following section**" in stripped
