"""Tests for Codex 0 inline edition variant preprocessing."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.codex_editions import (  # noqa: E402
    CodexEditionRenderError,
    edition_from_source_frontmatter,
    preprocess_codex_edition_blocks,
)
from engine.profile_resolver import resolve_profile  # noqa: E402
from engine.projection_plan import ProjectionPlan  # noqa: E402
from renderers.pandoc_renderer import PandocRenderer  # noqa: E402


def test_codex_edition_preprocessor_selects_requested_branch_and_strips_markers(tmp_path):
    src = tmp_path / "variant.md"
    src.write_text(
        "---\n"
        "title: Variant Test\n"
        "codex_edition: reader\n"
        "---\n\n"
        "Before.\n\n"
        "<!-- cx0:variant id=\"how-you-arrived-010\" fallback=\"johannah\" -->\n"
        "<!-- cx0:edition johannah -->\n"
        "Johannah prose with **Markdown**.\n"
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
    assert "Johannah prose" not in rewritten
    assert "cx0:" not in rewritten


def test_codex_edition_preprocessor_uses_declared_fallback(tmp_path):
    src = tmp_path / "fallback.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" fallback=\"johannah\" -->\n"
        "<!-- cx0:edition johannah -->\n"
        "Fallback prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    result = preprocess_codex_edition_blocks(src, tmp_path, "fallback", "family")
    rewritten = result.rewritten_source.read_text()

    assert "Fallback prose." in rewritten
    assert result.fallback_count == 1
    assert result.fallback_variant_ids == ["v1"]


def test_codex_edition_preprocessor_fails_without_selected_edition(tmp_path):
    src = tmp_path / "missing-edition.md"
    src.write_text(
        "<!-- cx0:variant id=\"v1\" -->\n"
        "<!-- cx0:edition johannah -->\n"
        "Private prose.\n"
        "<!-- cx0:endvariant -->\n"
    )

    with pytest.raises(CodexEditionRenderError, match="no branch for edition"):
        preprocess_codex_edition_blocks(src, tmp_path, "missing-edition", "reader")


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


def test_pandoc_renderer_leaves_other_renders_without_markers_unchanged(tmp_path):
    src = tmp_path / "ordinary.md"
    src.write_text("---\ntitle: Ordinary\n---\n\nPlain prose.\n")
    plan = ProjectionPlan(profile_id="keeper", render_id="ordinary", render_source=src)

    prepared = PandocRenderer()._prepare_codex_edition_source(plan, tmp_path, resolve_profile("keeper"))

    assert prepared.render_source == src
    assert prepared.boundary_assertions == {}
