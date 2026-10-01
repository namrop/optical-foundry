"""Tests for optional layout-image source blocks."""
from engine import source_preparation
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.layout_images import LayoutImageRenderError, preprocess_layout_image_blocks
from engine.manifest_compiler import MarkdownDocumentCompiler
from engine.profile_resolver import resolve_profile
from engine.projection_plan import ProjectionPlan


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
    assert "\\IfFileExists{wrapfig.sty}" not in rewritten
    assert "\\begin{wrapfigure}{r}{0.34\\textwidth}" in rewritten
    assert "\\OFDecorativeImage{width=\\linewidth}{assets/portrait.png}{vignette}" in rewritten
    assert "\\caption{Moonlit portrait}" in rewritten
    assert "\\graphicspath{{" in rewritten
    assert f"{{{tmp_path.as_posix()}/}}" in rewritten
    assert result.graphicspath_roots == [f"{tmp_path.as_posix()}/"]
    assert "```of-image" not in rewritten


def test_layout_image_wrap_accepts_general_tightening_controls(tmp_path):
    src = tmp_path / "wrap-tight.md"
    src.write_text(
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: wrap\n"
        "side: left\n"
        "width: 0.36\\textwidth\n"
        "image_width: 0.92\\linewidth\n"
        "lines: 18\n"
        "overhang: 0.04in\n"
        "sep: 0.055in\n"
        "intextsep: 0pt\n"
        "raise: -0.2\\baselineskip\n"
        "trim: 6pt 4pt 7pt 3pt\n"
        "clip: true\n"
        "```\n\n"
        "Text that should wrap around the image.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "wrap-tight")
    rewritten = result.rewritten_source.read_text()
    entry = result.figure_inventory[0]

    assert "\\setlength{\\OFWrapSavedColumnSep}{\\columnsep}\n\\setlength{\\columnsep}{0.055in}" in rewritten
    assert "\\setlength{\\OFWrapSavedInTextSep}{\\intextsep}\n\\setlength{\\intextsep}{0pt}" in rewritten
    assert "\\vspace*{-0.2\\baselineskip}" in rewritten
    assert "\\begin{wrapfigure}[18]{l}[0.04in]{0.36\\textwidth}" in rewritten
    assert "\\OFDecorativeImage{width=0.92\\linewidth,trim=6pt 4pt 7pt 3pt,clip}{assets/portrait.png}{}" in rewritten
    assert "\\end{wrapfigure}\n\\setlength{\\columnsep}{\\OFWrapSavedColumnSep}" in rewritten
    assert "\\setlength{\\intextsep}{\\OFWrapSavedInTextSep}" in rewritten
    assert entry["placement"] == "wrap"
    assert entry["wrapped_lines"] == 18
    assert entry["overhang"] == "0.04in"
    assert entry["sep"] == "0.055in"
    assert entry["intextsep"] == "0pt"
    assert entry["raise"] == "-0.2\\baselineskip"
    assert entry["trim"] == "6pt 4pt 7pt 3pt"
    assert entry["clip"] is True


@pytest.mark.parametrize("bad_value", ["0", "-1", "41", "two"])
def test_layout_image_wrap_rejects_invalid_wrapped_line_counts(tmp_path, bad_value):
    src = tmp_path / "wrap-bad-lines.md"
    src.write_text(
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: wrap\n"
        f"lines: {bad_value}\n"
        "```\n"
    )

    with pytest.raises(LayoutImageRenderError, match="lines must be an integer from 1 to 40"):
        preprocess_layout_image_blocks(src, tmp_path, "wrap-bad-lines")


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


def test_illumination_package_uses_wrapfigure_exclusion_not_hangindent_overlay():
    sty = Path("profiles/40_latex_import/styles/texmf/tex/latex/yugen/yugenillumination.sty").read_text()

    assert "\\RequirePackage{wrapfig}" in sty
    assert "\\begin{wrapfigure}[#3]{l}{\\dimexpr\\OFInitialWidth+\\OFInitialGap\\relax}" in sty
    assert "\\vspace*{\\dimexpr#5-.85\\baselineskip\\relax}" in sty
    assert "\\includegraphics[width=\\OFInitialWidth]{#1}" in sty
    assert "\\hangindent" not in sty
    assert "\\hangafter" not in sty
    assert "\\raisebox" not in sty


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


def test_image_initial_recipe_applies_defaults_and_records_recipe(tmp_path):
    src = tmp_path / "initial-recipe.md"
    src.write_text(
        "```of-initial\n"
        "recipe: codex0_a5_default\n"
        "path: assets/dropcaps/codex0/I.png\n"
        "```\n"
        "n the beginning, the threshold stood open.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "initial-recipe")
    rewritten = result.rewritten_source.read_text()
    entry = result.figure_inventory[0]

    assert "\\OFImageInitialSetup{assets/dropcaps/codex0/I.png}{.72in}{4}{.06in}{0in}{bottom}" in rewritten
    assert entry["recipe"] == "codex0_a5_default"
    assert entry["width"] == ".72in"
    assert entry["wrapped_lines"] == 4


def test_image_initial_recipe_allows_explicit_tuning_override(tmp_path):
    src = tmp_path / "initial-recipe-override.md"
    src.write_text(
        "```of-initial\n"
        "recipe: codex0_a5_default\n"
        "path: assets/dropcaps/codex0/I.png\n"
        "gap: .09in\n"
        "lines: 4\n"
        "```\n"
        "n the beginning, the threshold stood open.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "initial-recipe-override")
    rewritten = result.rewritten_source.read_text()
    entry = result.figure_inventory[0]

    assert "\\OFImageInitialSetup{assets/dropcaps/codex0/I.png}{.72in}{4}{.09in}{0in}{bottom}" in rewritten
    assert entry["recipe"] == "codex0_a5_default"


def test_image_initial_unknown_recipe_is_rejected(tmp_path):
    src = tmp_path / "initial-bad-recipe.md"
    src.write_text(
        "```of-initial\n"
        "recipe: missing_recipe\n"
        "path: assets/dropcaps/codex0/I.png\n"
        "```\n"
    )

    with pytest.raises(LayoutImageRenderError, match="unknown recipe"):
        preprocess_layout_image_blocks(src, tmp_path, "initial-bad-recipe")


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

    prepared = source_preparation.layout_images(plan, tmp_path / "render-out", resolve_profile(plan.profile_id))

    assert prepared.figure_inventory[0]["kind"] == "image_initial"
    assert prepared.boundary_assertions["image_initials_enabled"] is True
    assert prepared.boundary_assertions["image_initial_count"] == 1
    assert prepared.boundary_assertions["image_initial_default_alignment"] == "bottom"
    assert prepared.boundary_assertions["figure_count_by_kind"] == {"image_initial": 1}


def test_markdown_document_manifest_layout_images_include_original_source_root(tmp_path):
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "rendered"
    source_dir.mkdir()
    src = source_dir / "story.md"
    src.write_text(
        "---\n"
        "title: Story\n"
        "---\n\n"
        "```{=latex}\n"
        "\\includegraphics{assets/plates/title.png}\n"
        "```\n\n"
        "```of-initial\n"
        "path: assets/drop_caps_transparent/T.png\n"
        "width: .72in\n"
        "lines: 5\n"
        "align: top\n"
        "```\n"
        "he story begins.\n"
    )
    plan = MarkdownDocumentCompiler().compile(
        {
            "kind": "markdown_document",
            "schema_version": "document_manifest_v1",
            "document_id": "story_manifest",
            "profile": "mythic",
            "source": {"path": str(src)},
            "render": {"include_toc": False, "numbersections": False},
        }
    )

    prepared = source_preparation.layout_images(plan, output_dir, resolve_profile(plan.profile_id))

    roots = prepared.boundary_assertions["layout_image_graphicspath_roots"]
    assert f"{source_dir.as_posix()}/" in roots
    assert f"{output_dir.as_posix()}/" in roots
    rewritten = prepared.render_source.read_text()
    assert f"{{{source_dir.as_posix()}/}}" in rewritten
    assert "\\includegraphics{assets/plates/title.png}" in rewritten
    assert "\\OFImageInitialSetup{assets/drop_caps_transparent/T.png}{.72in}{5}" in rewritten


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

    prepared = source_preparation.layout_images(plan, tmp_path / "render-out", resolve_profile(plan.profile_id))

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

    prepared = source_preparation.layout_images(plan, tmp_path / "render-out", resolve_profile(plan.profile_id))

    assert prepared.render_source == src
    assert prepared.figure_inventory == []
    assert prepared.boundary_assertions == {}


def test_layout_image_source_header_includes_reach_the_preamble(tmp_path):
    src = tmp_path / "layout-image-font-overlay.md"
    src.write_text(
        "```of-image\n"
        "path: assets/portrait.png\n"
        "placement: wrap\n"
        "```\n"
    )
    plan = ProjectionPlan(
        profile_id="mythic",
        render_id="layout-image-font-overlay",
        render_source=src,
        output_format="pdf",
        output_extension=".pdf",
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = source_preparation.layout_images(plan, tmp_path / "render-out", resolve_profile(plan.profile_id))
    # The layout preprocessor's preamble lines reach the render's one preamble
    # (engine/preamble.py) whatever overlays the render also uses.
    from engine.preamble import Preamble

    preamble = Preamble()
    preamble.add_source(prepared.render_source)
    preamble.add("draft", "\\setkeys{Gin}{draft=true}")
    text = preamble.text()
    assert "\\usepackage{wrapfig}" in text
    assert "\\usepackage{tikz}" in text


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

        prepared = source_preparation.layout_images(plan, tmp_path / f"render-out-{profile_id}", resolve_profile(plan.profile_id))
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


# --- Displayed-image whitespace contract (Luis-ruled 2026-08-11, folios 168/204) ---
#
# "there is too much whitespace around the image. it should be comparable to a
# hinge. across the whole work." A displayed image must carry the hinge ornament's
# own envelope, and must not smuggle extra air in as blank canvas inside the asset.


def _write_png(path: Path, size, ink_box, *, transparent_margin=True):
    """A PNG with a solid ink rectangle and a blank margin around it."""
    Image = pytest.importorskip("PIL.Image", reason="Pillow drives margin measurement")
    fill = (0, 0, 0, 0) if transparent_margin else (255, 255, 255, 255)
    image = Image.new("RGBA", size, fill)
    for x in range(ink_box[0], ink_box[2]):
        for y in range(ink_box[1], ink_box[3]):
            image.putpixel((x, y), (0, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def test_block_placement_uses_the_hinge_envelope_not_bare_center(tmp_path):
    src = tmp_path / "block-envelope.md"
    src.write_text(
        "---\ntitle: Block Envelope\n---\n\n"
        "Prose above.\n\n"
        "```of-image\n"
        "path: assets/vignette.png\n"
        "placement: block\n"
        "width: 2.4in\n"
        "```\n\n"
        "Prose below.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "block-envelope")
    rewritten = result.rewritten_source.read_text()

    # 2\baselineskip is codex0_composition.lua's hinge_ornament_gap, verbatim.
    assert "\\begin{OFDisplayedFigure}[2\\baselineskip]" in rewritten
    assert "\\end{OFDisplayedFigure}" in rewritten
    assert "\\begin{center}" not in rewritten
    assert "\\newenvironment{OFDisplayedFigure}" in rewritten
    assert result.figure_inventory[0]["gap"] == "2\\baselineskip"


def test_block_placement_gap_is_tunable_per_image(tmp_path):
    src = tmp_path / "block-gap.md"
    src.write_text(
        "```of-image\n"
        "path: assets/vignette.png\n"
        "placement: block\n"
        "width: 2.4in\n"
        "gap: 1\\baselineskip\n"
        "```\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "block-gap")

    assert "\\begin{OFDisplayedFigure}[1\\baselineskip]" in result.rewritten_source.read_text()


def test_block_placement_crops_the_blank_margin_the_asset_ships(tmp_path):
    # 40% blank down each side, 25% across the top and bottom: the shape two object
    # vignette extracts actually have.
    _write_png(tmp_path / "assets" / "object-a.png", (100, 100), (40, 25, 60, 75))
    src = tmp_path / "trimmed.md"
    src.write_text(
        "```of-image\n"
        "path: assets/object-a.png\n"
        "placement: block\n"
        "width: 2in\n"
        "```\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "trimmed")
    rewritten = result.rewritten_source.read_text()
    entry = result.figure_inventory[0]

    assert entry["auto_trim"] is not None
    assert entry["auto_trim"]["source"].endswith("object-a.png")
    # 40% margin less the 2% bleed on each side leaves 24% of the width retained...
    assert entry["auto_trim"]["retained_width"] == pytest.approx(0.24, abs=0.02)
    # ...and the declared width shrinks by exactly that, so the VISIBLE object keeps
    # the size it had. This removes whitespace; it must never resize artwork.
    assert entry["width"].endswith("in")
    assert float(entry["width"][:-2]) == pytest.approx(2 * 0.24, abs=0.04)
    assert entry["auto_trim"]["authored_width"] == "2in"
    # The inventory keeps auditing the authored reference; the render-local twin
    # is recorded under auto_trim and is what the emitted LaTeX points at.
    assert entry["path"] == "assets/object-a.png"
    assert "__oftrim_" in entry["auto_trim"]["trimmed"]
    assert (tmp_path / entry["auto_trim"]["trimmed"]).is_file()
    assert entry["auto_trim"]["trimmed"] in rewritten


def test_auto_trim_is_deterministic_across_runs(tmp_path):
    _write_png(tmp_path / "assets" / "object-a.png", (100, 100), (40, 25, 60, 75))
    src = tmp_path / "stable.md"
    src.write_text(
        "```of-image\npath: assets/object-a.png\nplacement: block\nwidth: 2in\n```\n"
    )

    first = preprocess_layout_image_blocks(src, tmp_path, "stable")
    second = preprocess_layout_image_blocks(src, tmp_path, "stable")

    assert first.figure_inventory[0]["auto_trim"]["trimmed"] == second.figure_inventory[0]["auto_trim"]["trimmed"]


def test_auto_trim_leaves_a_full_bleed_asset_alone(tmp_path):
    _write_png(tmp_path / "assets" / "plate.png", (100, 100), (0, 0, 100, 100))
    src = tmp_path / "fullbleed.md"
    src.write_text(
        "```of-image\npath: assets/plate.png\nplacement: block\nwidth: 2in\n```\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "fullbleed")
    entry = result.figure_inventory[0]

    assert entry["auto_trim"] is None
    assert entry["path"] == "assets/plate.png"
    assert entry["width"] == "2in"


def test_auto_trim_defers_to_an_authored_trim_and_to_opt_out(tmp_path):
    _write_png(tmp_path / "assets" / "object-a.png", (100, 100), (40, 25, 60, 75))
    for body, label in (
        ("trim: 1pt 1pt 1pt 1pt\nclip: true\n", "authored-trim"),
        ("auto_trim: false\n", "opted-out"),
    ):
        src = tmp_path / f"{label}.md"
        src.write_text(
            "```of-image\npath: assets/object-a.png\nplacement: block\nwidth: 2in\n" + body + "```\n"
        )
        result = preprocess_layout_image_blocks(src, tmp_path, label)
        assert result.figure_inventory[0]["auto_trim"] is None, label
        assert result.figure_inventory[0]["path"] == "assets/object-a.png", label


def test_wrap_placement_is_left_alone(tmp_path):
    # A wrap has prose beside it rather than above and below it; its space is
    # \intextsep / \columnsep, and the wrapped vignette reads correctly today.
    # Neither the hinge envelope nor the crop belongs to it.
    _write_png(tmp_path / "assets" / "can.png", (100, 100), (40, 25, 60, 75))
    src = tmp_path / "wrap-untouched.md"
    src.write_text(
        "```of-image\n"
        "path: assets/can.png\n"
        "placement: wrap\n"
        "align: right\n"
        "width: 1.5in\n"
        "lines: 10\n"
        "```\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "wrap-untouched")
    rewritten = result.rewritten_source.read_text()
    entry = result.figure_inventory[0]

    assert entry["auto_trim"] is None
    assert entry["width"] == "1.5in"
    assert entry["gap"] is None
    assert "\\begin{wrapfigure}[10]{r}{1.5in}" in rewritten
    assert "\\begin{OFDisplayedFigure}" not in rewritten


def test_raw_centered_vignette_gets_the_same_contract(tmp_path):
    # Two object vignettes — both named in the folio-168 note —
    # are raw \begin{center}\includegraphics lines in source, never of-image blocks.
    # An of-image-only fix would have missed exactly the instances Luis cited.
    asset = _write_png(tmp_path / "media" / "object-b.png", (100, 100), (40, 25, 60, 75))
    src = tmp_path / "raw-vignette.md"
    src.write_text(
        "---\ntitle: Raw Vignette\n---\n\n"
        "Prose above.\n\n"
        "```{=latex}\n"
        f"\\begin{{center}}\\includegraphics[width=1.9in]{{{asset}}}\\end{{center}}\n"
        "```\n\n"
        "Prose below.\n"
    )

    result = preprocess_layout_image_blocks(src, tmp_path, "raw-vignette")
    rewritten = result.rewritten_source.read_text()
    entry = result.figure_inventory[0]

    assert entry["origin"] == "raw_centered_graphic"
    assert entry["gap"] == "2\\baselineskip"
    assert entry["auto_trim"] is not None
    assert "\\begin{OFDisplayedFigure}[2\\baselineskip]" in rewritten
    assert "\\newenvironment{OFDisplayedFigure}" in rewritten
    assert "\\usepackage{tikz}" in rewritten
    assert "\\begin{center}\\includegraphics" not in rewritten


@pytest.mark.parametrize(
    "line",
    [
        # Full-page plates: out of scope by Luis's framing, and excluded structurally.
        r"\begin{center}\includegraphics[width=\textwidth,height=0.90\textheight,keepaspectratio]{\detokenize{/tmp/plate.png}}\end{center}",
        r"\begin{center}\includegraphics[width=\textwidth]{/tmp/plate.png}\end{center}",
        r"\begin{center}\includegraphics[height=0.95in]{/tmp/plate.png}\end{center}",
        # Not line-initial: a quoted or commented placement directive stays prose.
        r"> \begin{center}\includegraphics[width=3.2in]{/tmp/plate.png}\end{center}",
    ],
)
def test_raw_centered_pass_leaves_full_page_plates_and_quoted_lines_alone(tmp_path, line):
    src = tmp_path / "plate.md"
    src.write_text("---\ntitle: Plate\n---\n\n" + line + "\n")

    result = preprocess_layout_image_blocks(src, tmp_path, "plate")
    rewritten = result.rewritten_source.read_text()

    assert line in rewritten
    assert "OFDisplayedFigure" not in rewritten
    assert not [entry for entry in result.figure_inventory if entry.get("kind") == "layout_image"]
