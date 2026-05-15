"""Tests for optional layout-image source blocks."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.layout_images import LayoutImageRenderError, preprocess_layout_image_blocks
from engine.profile_resolver import resolve_profile
from engine.projection_plan import ProjectionPlan
from renderers.pandoc_renderer import PandocRenderer


def test_layout_image_wrap_block_rewrites_to_wrapfig_with_header_includes(tmp_path):
    src = tmp_path / "wrap-image.md"
    src.write_text(
        "---\n"
        "title: Wrap Image\n"
        "---\n\n"
        "Lead paragraph before the image.\n\n"
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: wrap\n"
        "align: right\n"
        "width: 0.34\\textwidth\n"
        "edge: vignette\n"
        "caption: Moonlit portrait\n"
        "```\n\n"
        "Text that should wrap around the image.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "wrap-image")
    rewritten = result.rewritten_source.read_text()

    assert result.changed is True
    assert result.figure_inventory[0]["kind"] == "layout_image"
    assert result.figure_inventory[0]["placement"] == "wrap"
    assert result.figure_inventory[0]["edge"] == "vignette"
    assert "\\usepackage{wrapfig}" in rewritten
    assert "\\begin{wrapfigure}{r}{0.34\\textwidth}" in rewritten
    assert "\\OFDecorativeImage{width=\\linewidth}{assets/portrait.png}{vignette}" in rewritten
    assert "\\caption{Moonlit portrait}" in rewritten
    assert "\\graphicspath{{" in rewritten
    assert f"{{{tmp_path.as_posix()}/}}" in rewritten
    assert result.graphicspath_roots == [f"{tmp_path.as_posix()}/"]
    assert "```of-image" not in rewritten


def test_layout_image_wrapfig_package_is_vendored_and_resolves_through_profile_env():
    kpsewhich = shutil.which("kpsewhich") or "/Library/TeX/texbin/kpsewhich"
    if not Path(kpsewhich).exists():
        pytest.skip("kpsewhich not available")

    resolved = resolve_profile("mythic")
    env = os.environ.copy()
    env.update(resolved.render_environment.env_overrides())
    result = subprocess.run(
        [kpsewhich, "wrapfig.sty"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )

    assert result.returncode == 0
    path = Path(result.stdout.strip())
    assert path.name == "wrapfig.sty"
    assert path == Path("profiles/40_latex_import/styles/texmf/tex/latex/generic/wrapfig.sty").resolve()


def test_illumination_package_resolves_through_profile_env():
    kpsewhich = shutil.which("kpsewhich") or "/Library/TeX/texbin/kpsewhich"
    if not Path(kpsewhich).exists():
        pytest.skip("kpsewhich not available")

    resolved = resolve_profile("mythic")
    env = os.environ.copy()
    env.update(resolved.render_environment.env_overrides())
    result = subprocess.run(
        [kpsewhich, "yugenillumination.sty"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )

    assert result.returncode == 0
    path = Path(result.stdout.strip())
    assert path == Path("profiles/40_latex_import/styles/texmf/tex/latex/yugen/yugenillumination.sty").resolve()


def test_layout_image_adds_source_and_output_graphicspath_roots(tmp_path):
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "render"
    source_dir.mkdir()
    src = source_dir / "image-root-test.md"
    src.write_text(
        "```of-image\n"
        "path: assets/local.png\n"
        "placement: inline\n"
        "```\n"
    )

    result = preprocess_layout_image_blocks(src, output_dir, "image-root-test")
    rewritten = result.rewritten_source.read_text()

    expected_roots = [f"{source_dir.as_posix()}/", f"{output_dir.as_posix()}/"]
    assert result.graphicspath_roots == expected_roots
    assert f"\\graphicspath{{{{{expected_roots[0]}}}{{{expected_roots[1]}}}}}" in rewritten


def test_layout_image_rejects_tex_unsafe_source_directory_with_actionable_error(tmp_path):
    bad_source_dir = tmp_path / "source%bad"
    bad_source_dir.mkdir()
    src = bad_source_dir / "unsafe-root.md"
    src.write_text(
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: inline\n"
        "```\n"
    )

    with pytest.raises(LayoutImageRenderError) as excinfo:
        preprocess_layout_image_blocks(src, tmp_path / "render-out", "unsafe-root")

    message = str(excinfo.value)
    assert "source/output directory" in message
    assert "TeX-unsafe characters" in message
    assert "Move the source/render output to a path without" in message
    assert "%" in message


def test_image_initial_block_rewrites_to_bottom_aligned_macro_with_live_text(tmp_path):
    src = tmp_path / "initial-image.md"
    src.write_text(
        "# Initial Image\n\n"
        "```of-initial\n"
        "path: assets/dropcaps/oasis/T.png\n"
        "width: .84in\n"
        "lines: 4\n"
        "gap: .08in\n"
        "raise: 0in\n"
        "align: bottom\n"
        "```\n"
        "hey awoke on a beach at the edge of the desert.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "initial-image")
    rewritten = result.rewritten_source.read_text()

    assert result.changed is True
    assert result.figure_inventory[0]["kind"] == "image_initial"
    assert result.figure_inventory[0]["alignment"] == "bottom"
    assert result.figure_inventory[0]["wrapped_lines"] == 4
    assert "\\usepackage{yugenillumination}" in rewritten
    assert "\\OFImageInitialSetup{assets/dropcaps/oasis/T.png}{.84in}{4}{.08in}{0in}{bottom}" in rewritten
    assert "hey awoke on a beach" in rewritten
    assert "```of-initial" not in rewritten


def test_image_initial_top_alignment_and_raise_are_explicit(tmp_path):
    src = tmp_path / "initial-image-top.md"
    src.write_text(
        "```of-initial\n"
        "path: assets/dropcaps/codex0/I.png\n"
        "width: .72in\n"
        "lines: 3\n"
        "gap: .06in\n"
        "align: top\n"
        "raise: -.1in\n"
        "```\n"
        "n the beginning, the threshold stood open.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "initial-image-top")
    rewritten = result.rewritten_source.read_text()

    assert "\\OFImageInitialSetup{assets/dropcaps/codex0/I.png}{.72in}{3}{.06in}{-.1in}{top}" in rewritten
    assert result.figure_inventory[0]["alignment"] == "top"


def test_pandoc_renderer_records_image_initial_evidence(tmp_path):
    src = tmp_path / "initial-evidence.md"
    src.write_text(
        "```of-initial\n"
        "path: assets/dropcaps/oasis/T.png\n"
        "width: .84in\n"
        "lines: 4\n"
        "gap: .08in\n"
        "align: bottom\n"
        "```\n"
        "hey awoke on a beach.\n"
    )
    plan = ProjectionPlan(
        profile_id="mythic",
        render_id="initial-evidence",
        render_source=src,
        output_format="pdf",
        output_extension=".pdf",
        figure_inventory=[],
        boundary_assertions={},
    )

    prepared = PandocRenderer()._prepare_layout_image_source(plan, tmp_path / "render-out")

    assert prepared.figure_inventory[0]["kind"] == "image_initial"
    assert prepared.boundary_assertions["image_initials_enabled"] is True
    assert prepared.boundary_assertions["image_initial_count"] == 1
    assert prepared.boundary_assertions["image_initial_default_alignment"] == "bottom"
    assert prepared.boundary_assertions["figure_count_by_kind"] == {"image_initial": 1}


def test_layout_image_absolute_block_rewrites_to_shipout_overlay(tmp_path):
    src = tmp_path / "absolute-image.md"
    src.write_text(
        "# Absolute Image\n\n"
        "```of-image\n"
        "path: assets/sigil.png\n"
        "placement: absolute\n"
        "anchor: north east\n"
        "x: -0.35in\n"
        "y: -0.6in\n"
        "width: 1.2in\n"
        "opacity: 0.82\n"
        "edge: fade\n"
        "```\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "absolute-image")
    rewritten = result.rewritten_source.read_text()

    assert rewritten.startswith("---\n")
    assert "\\usepackage{eso-pic}" in rewritten
    assert "\\AddToShipoutPictureFG*" in rewritten
    assert "current page.north east" in rewritten
    assert "xshift=-0.35in,yshift=-0.6in" in rewritten
    assert "opacity=0.82" in rewritten
    assert "\\OFDecorativeImage{width=1.2in}{assets/sigil.png}{fade}" in rewritten


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../secret.png",
        "/tmp/secret.png",
        "https://example.test/portrait.png",
        "assets/portrait%20.png",
        r"assets/\\input.png",
        "assets/portrait#frag.png",
        "assets/portrait{bad}.png",
    ],
)
def test_layout_image_rejects_unsafe_paths(tmp_path, unsafe_path):
    src = tmp_path / "unsafe-image.md"
    src.write_text(
        "```of-image\n"
        f"path: {unsafe_path}\n"
        "placement: wrap\n"
        "```\n"
    )

    with pytest.raises(LayoutImageRenderError, match="relative image/PDF path"):
        preprocess_layout_image_blocks(src, tmp_path, "unsafe-image")


def test_layout_image_rejects_negative_widths(tmp_path):
    src = tmp_path / "negative-width.md"
    src.write_text(
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: absolute\n"
        "x: -0.35in\n"
        "width: -1.2in\n"
        "```\n"
    )

    with pytest.raises(LayoutImageRenderError, match="width values must be positive"):
        preprocess_layout_image_blocks(src, tmp_path, "negative-width")


def test_pandoc_renderer_prepares_layout_image_source_before_pandoc(tmp_path):
    src = tmp_path / "layout-image-input.md"
    src.write_text(
        "---\ntitle: Layout Image Input\n---\n\n"
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: wrap\n"
        "align: left\n"
        "width: 0.30\\textwidth\n"
        "```\n"
    )
    plan = ProjectionPlan(
        profile_id="mythic-letter-johannah",
        render_id="layout-image-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )

    prepared = PandocRenderer()._prepare_layout_image_source(plan, tmp_path / "render-out")

    assert prepared.render_source != src
    assert "```of-image" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "layout_image"
    assert prepared.boundary_assertions["layout_images_enabled"] is True
    assert prepared.boundary_assertions["layout_image_count"] == 1
    assert prepared.boundary_assertions["layout_image_supported_profiles"] == "pdf_latex_profiles"
    assert prepared.boundary_assertions["layout_image_profile_family"] == "stationery_art"
    roots = prepared.boundary_assertions["layout_image_graphicspath_roots"]
    assert roots[:2] == [
        f"{tmp_path.as_posix()}/",
        f"{(tmp_path / 'render-out').as_posix()}/",
    ]
    assert str(Path("profiles/40_latex_import").resolve()).rstrip("/") + "/" in roots
    assert prepared.boundary_assertions["figure_count_by_kind"] == {"layout_image": 1}


def test_pandoc_renderer_layout_images_are_pdf_latex_gated(tmp_path):
    src = tmp_path / "layout-image-html-input.md"
    src.write_text(
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: wrap\n"
        "```\n"
    )
    plan = ProjectionPlan(
        profile_id="mythic-letter-johannah",
        render_id="layout-image-html-input",
        render_source=src,
        output_format="html",
        output_extension=".html",
        figure_inventory=[],
        boundary_assertions={},
    )

    prepared = PandocRenderer()._prepare_layout_image_source(plan, tmp_path / "render-out")

    assert prepared.render_source == src
    assert prepared.figure_inventory == []
    assert prepared.boundary_assertions == {}


def test_pandoc_renderer_layout_images_support_mythic_pdf_profiles(tmp_path):
    for profile_id in ("mythic", "mythic-letter", "mythic-letter-johannah"):
        src = tmp_path / f"{profile_id}.md"
        src.write_text(
            "```of-image\n"
            "path: assets/mythic_letter/compass_star.png\n"
            "placement: inline\n"
            "width: 0.5in\n"
            "edge: soft\n"
            "```\n"
        )
        plan = ProjectionPlan(
            profile_id=profile_id,
            render_id=profile_id,
            render_source=src,
            output_format="pdf",
            output_extension=".pdf",
            figure_inventory=[],
            boundary_assertions={},
        )

        prepared = PandocRenderer()._prepare_layout_image_source(plan, tmp_path / f"render-out-{profile_id}")
        rewritten = prepared.render_source.read_text()

        assert prepared.render_source != src
        assert prepared.boundary_assertions["layout_images_enabled"] is True
        assert prepared.boundary_assertions["layout_image_supported_profiles"] == "pdf_latex_profiles"
        assert prepared.figure_inventory[0]["placement"] == "inline"
        assert "\\OFDecorativeImage{width=0.5in}{assets/mythic_letter/compass_star.png}{soft}" in rewritten
        assert "\\begin{center}" not in rewritten


def test_layout_image_preserves_existing_header_includes(tmp_path):
    src = tmp_path / "existing-header-includes.md"
    src.write_text(
        "---\n"
        "title: Existing Includes\n"
        "header-includes:\n"
        "  - \\usepackage{microtype}\n"
        "---\n\n"
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: block\n"
        "width: 1in\n"
        "```\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "existing-header-includes")
    rewritten = result.rewritten_source.read_text()

    assert "- \\usepackage{microtype}" in rewritten
    assert "- \\usepackage{graphicx}" in rewritten
    assert "- \\usepackage{tikz}" in rewritten
    assert rewritten.index("- \\usepackage{microtype}") < rewritten.index("- \\usepackage{graphicx}")
