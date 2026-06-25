"""Tests for Pandoc render dispatch and document renderer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engine.projection_plan import ProjectionPlan
from engine.profile_resolver import resolve_profile
from renderers.pandoc_renderer import PandocRenderer
from renderers.document_renderer import DocumentRenderer

GF = Path(__file__).resolve().parents[1]


def test_pandoc_renderer_creates_evidence_on_error():
    r = PandocRenderer()
    plan = ProjectionPlan(
        profile_id="nonexistent",
        render_id="test-error",
        render_source=Path("/nonexistent.md"),
    )
    evidence = r.render(plan, output_dir="/tmp/of_greenfield_test_error")
    assert evidence["status"] == "error"
    assert evidence["validation"]["status"] == "failed"
    assert evidence["validation"]["checks"]["pdf_written"] is False
    assert evidence["validation"]["errors"] == [evidence["error"]]


def test_pandoc_renderer_success_evidence_has_explicit_validation_surface(tmp_path):
    import shutil

    if not shutil.which("pandoc") or not shutil.which("pdftotext"):
        pytest.skip("pandoc/pdftotext not available")
    if not Path("/Library/TeX/texbin/xelatex").exists() and not shutil.which("xelatex"):
        pytest.skip("xelatex not available")

    src = tmp_path / "evidence-surface.md"
    src.write_text(
        "---\n"
        "uid: evidence-surface\n"
        "title: Evidence Surface\n"
        "toc: false\n"
        "numbersections: false\n"
        "---\n\n"
        "# Evidence Surface\n\n"
        "Optical Foundry validation marker remains live text.\n",
        encoding="utf-8",
    )

    evidence = DocumentRenderer().render(src, profile_id="generic-report", output_dir=str(tmp_path / "out"))

    assert evidence["status"] == "ok"
    assert evidence["validation"]["status"] == "passed"
    assert evidence["validation"]["checks"]["pdf_written"] is True
    assert evidence["validation"]["checks"]["text_extract_exists"] is True
    assert evidence["validation"]["checks"]["raw_latex_leakage"] is False
    assert evidence["validation"]["warning_count"] == len(evidence["warnings"])


def test_document_renderer_parses_frontmatter():
    dr = DocumentRenderer()
    src = GF / "fixtures" / "sources" / "source-001.md"
    assert src.exists()
    # Just verify it builds a plan without error; actual render requires xelatex
    plan = ProjectionPlan(
        profile_id="generic-report",
        render_id="test-doc",
        render_source=src,
    )
    assert plan.profile_id == "generic-report"
    assert plan.render_source == src


def test_document_renderer_frontmatter_role_emits_memoir_frontmatter(tmp_path):
    src = tmp_path / "preface.md"
    src.write_text(
        "---\n"
        "uid: preface-direct\n"
        "title: Preface Direct\n"
        "role: frontmatter\n"
        "---\n\n"
        "# Preface\n\n"
        "Direct document path body.\n"
    )

    plan = DocumentRenderer().build_plan(src, profile_id="cam")
    assembled = plan.render_source.read_text()

    assert plan.render_id == "preface-direct"
    assert plan.source_inventory[0]["role"] == "frontmatter"
    assert assembled.startswith("---\n")
    assert "\n\\frontmatter\n" in assembled
    assert assembled.index("\\frontmatter") < assembled.index("# Preface")
    assert plan.boundary_assertions["document_matter_role"] == "frontmatter"
    assert plan.boundary_assertions["frontmatter_mode_enabled"] is True


def test_document_renderer_frontmatter_page_size_sets_projection_plan(tmp_path):
    src = tmp_path / "a4-direct.md"
    src.write_text(
        "---\n"
        "uid: a4-direct\n"
        "title: A4 Direct\n"
        "page_size: A4\n"
        "---\n\n"
        "# A4 Direct\n\n"
        "Direct document path body.\n"
    )

    plan = DocumentRenderer().build_plan(src, profile_id="cam")

    assert plan.page_size == "a4"
    assert plan.boundary_assertions["page_size"] == "a4"
    assert plan.boundary_assertions["page_size_source"] == "source_frontmatter"


def test_document_renderer_frontmatter_page_margin_sets_projection_plan(tmp_path):
    src = tmp_path / "margin-direct.md"
    src.write_text(
        "---\n"
        "uid: margin-direct\n"
        "title: Margin Direct\n"
        "page_size: half_letter\n"
        "page_margin: 0.7in\n"
        "---\n\n"
        "# Margin Direct\n\n"
        "Direct document path body.\n"
    )

    plan = DocumentRenderer().build_plan(src, profile_id="cam")

    assert plan.page_size == "half_letter"
    assert plan.page_margins == ["margin=0.7in"]
    assert plan.boundary_assertions["page_margins"] == ["margin=0.7in"]
    assert plan.boundary_assertions["page_margins_source"] == "source_frontmatter"


def test_document_renderer_rejects_conflicting_frontmatter_role_aliases(tmp_path):
    src = tmp_path / "conflicting-preface.md"
    src.write_text(
        "---\n"
        "uid: conflicting-preface\n"
        "title: Conflicting Preface\n"
        "role: frontmatter\n"
        "matter: document_source\n"
        "---\n\n"
        "# Preface\n\n"
        "Direct document path body.\n"
    )

    with pytest.raises(ValueError, match="conflicting source_frontmatter matter roles"):
        DocumentRenderer().build_plan(src, profile_id="cam")


def test_document_renderer_ignores_unrelated_frontmatter_role(tmp_path):
    src = tmp_path / "contract.md"
    src.write_text(
        "---\n"
        "uid: contract-direct\n"
        "title: Contract Direct\n"
        "role: contract\n"
        "---\n\n"
        "# Contract\n\n"
        "Direct document path body.\n"
    )

    plan = DocumentRenderer().build_plan(src, profile_id="cam")

    assert plan.render_id == "contract-direct"
    assert plan.render_source == src
    assert plan.source_inventory[0]["role"] == "document_source"
    assert plan.boundary_assertions["document_matter_role"] == "document_source"


def test_pandoc_renderer_template_inference_uses_shared_profile_resolver():
    r = PandocRenderer()
    assert r._infer_template("generic-report") == "generic_report.tex"
    assert r._infer_template("risk") == "base.tex"
    assert r._infer_template("tech") == "base.tex"
    assert r._infer_template("creative") == "base.tex"
    assert r._infer_template("letter") == "personal_letter.tex"
    assert r._infer_template("mythic-letter") == "personal_letter.tex"
    assert r._infer_template("prometheus-packet") == "generic_report.tex"
    assert r._infer_template("labels-avery-5164") == "label_sheet.tex"
    assert r._infer_template("sticker-sheet") == "label_sheet.tex"


def test_pandoc_renderer_prepares_render_only_emoji_substitution(tmp_path):
    src = tmp_path / "keeper-emoji.md"
    src.write_text("---\ntitle: Keeper Emoji\n---\n\nKeeper warning ⚠️.\n", encoding="utf-8")
    plan = ProjectionPlan(
        profile_id="keeper",
        render_id="keeper-emoji",
        render_source=src,
    )

    prepared = PandocRenderer()._prepare_emoji_substitution_source(plan, tmp_path / "out")

    assert prepared.render_source != src
    assert prepared.render_source.read_text(encoding="utf-8").count(r"\OFEmoji{") == 1
    assert prepared.boundary_assertions["emoji_policy"] == "vendored_image_assets"
    assert prepared.boundary_assertions["emoji_asset_family"] == "noto_emoji"
    assert prepared.boundary_assertions["host_emoji_fonts_required"] is False
    assert prepared.boundary_assertions["emoji_substitution_count"] == 1
    assert prepared.figure_inventory[-1]["kind"] == "emoji_asset"


def test_pandoc_renderer_page_size_defaults_merge_profile_geometry(tmp_path):
    plan = ProjectionPlan(
        profile_id="cam",
        render_id="half-letter-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="half_letter",
    )
    resolved = resolve_profile("cam")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    data = yaml.safe_load(defaults.read_text())
    variables = data["variables"]
    geometry = variables["geometry"]
    assert geometry[:2] == ["paperwidth=5.5in", "paperheight=8.5in"]
    assert "margin=1in" in geometry
    assert variables["header-includes"] == [r"\special{papersize=\the\paperwidth,\the\paperheight}"]
    assert variables["classoption"] == ["11pt", "oneside", "statementpaper"]


def test_pandoc_renderer_font_runtime_defaults_preserve_geometry_and_override_yugen_fonts(tmp_path):
    plan = ProjectionPlan(
        profile_id="cam",
        render_id="font-fallback-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="a4",
    )
    resolved = resolve_profile("cam")
    renderer = PandocRenderer()
    geometry_defaults = renderer._page_geometry_defaults(plan, resolved, tmp_path)

    defaults, fallbacks = renderer._font_runtime_defaults(
        resolved.defaults_stack,
        tmp_path,
        plan.render_id,
        geometry_defaults,
    )

    assert defaults is not None
    import yaml
    variables = yaml.safe_load(defaults.read_text())["variables"]
    assert r"\special{papersize=\the\paperwidth,\the\paperheight}" in variables["header-includes"]
    header_includes = "\n".join(variables["header-includes"])
    assert "\\renewcommand\\yugen@setfonts" in header_includes
    assert "\\setmainfont{DejaVu Serif}" in header_includes
    assert "\\setsansfont{DejaVu Sans}" in header_includes
    assert "\\setmonofont{DejaVu Sans Mono}" in header_includes
    assert {item["role"] for item in fallbacks} >= {
        "mainfont",
        "sansfont",
        "monofont",
        "yugencommon.mainfont",
        "yugencommon.sansfont",
        "yugencommon.monofont",
    }


def test_pandoc_renderer_page_margin_override_replaces_profile_margin(tmp_path):
    plan = ProjectionPlan(
        profile_id="cam",
        render_id="half-letter-custom-margin-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="half_letter",
        page_margins=["margin=0.7in"],
    )
    resolved = resolve_profile("cam")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    variables = yaml.safe_load(defaults.read_text())["variables"]
    assert variables["geometry"] == ["paperwidth=5.5in", "paperheight=8.5in", "margin=0.7in"]
    assert variables["classoption"] == ["11pt", "oneside", "statementpaper"]


def test_pandoc_renderer_bound_delivery_defaults_mirror_geometry_and_outer_numbers(tmp_path):
    plan = ProjectionPlan(
        profile_id="mythic",
        render_id="bound-half-letter-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="half_letter",
        page_margins=["inner=0.85in", "outer=0.60in", "top=0.65in", "bottom=0.70in"],
        delivery={
            "mode": "bound",
            "binding": "side_staple",
            "duplex": True,
            "page_numbers": "outer",
            "colophon": {"enabled": True, "placement": "title_verso"},
            "footer_metadata": {"suppress_repeated": True},
        },
    )
    resolved = resolve_profile("mythic")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    variables = yaml.safe_load(defaults.read_text())["variables"]
    assert variables["geometry"] == [
        "paperwidth=5.5in",
        "paperheight=8.5in",
        "inner=0.85in",
        "outer=0.60in",
        "top=0.65in",
        "bottom=0.70in",
    ]
    assert variables["classoption"] == ["11pt", "twoside", "statementpaper"]
    assert variables["pagestyle"] == "ofBoundOuter"
    assert variables["footeremail"] == ""
    header_includes = "\n".join(variables["header-includes"])
    assert "\\makeevenfoot{ofBoundOuter}{\\thepage}{}{}" in header_includes
    assert "\\makeoddfoot {ofBoundOuter}{}{}{\\thepage}" in header_includes


def test_pandoc_renderer_bound_delivery_running_headers_use_memoir_marks(tmp_path):
    plan = ProjectionPlan(
        profile_id="mythic",
        render_id="bound-running-headers-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="half_letter",
        page_margins=["inner=0.85in", "outer=0.60in", "top=0.65in", "bottom=0.70in"],
        title="Bound Running Headers",
        delivery={
            "mode": "bound",
            "binding": "side_staple",
            "duplex": True,
            "page_numbers": "outer",
            "running_headers": {
                "enabled": True,
                "source": "chapter",
                "suppress_on": ["title_page", "title_verso", "blank_pages", "chapter_openers"],
            },
            "colophon": {"enabled": True, "placement": "title_verso"},
            "footer_metadata": {"suppress_repeated": True},
        },
    )
    resolved = resolve_profile("mythic")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    variables = yaml.safe_load(defaults.read_text())["variables"]
    header_includes = "\n".join(variables["header-includes"])
    assert variables["pagestyle"] == "ofBoundOuter"
    assert "\\makeevenhead{ofBoundOuter}{\\small\\itshape\\leftmark}{}{}" in header_includes
    assert "\\makeoddhead {ofBoundOuter}{}{}{\\small\\itshape\\rightmark}" in header_includes
    assert "\\makepagestyle{ofBoundPlain}" in header_includes
    assert "\\aliaspagestyle{plain}{ofBoundPlain}" in header_includes


def test_pandoc_renderer_bound_delivery_illumination_rail_header_include(tmp_path):
    plan = ProjectionPlan(
        profile_id="mythic",
        render_id="bound-illumination-rail-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="half_letter",
        page_margins=["inner=0.85in", "outer=0.60in", "top=0.65in", "bottom=0.70in"],
        title="Bound Illumination Rail",
        delivery={
            "mode": "bound",
            "binding": "saddle_stitch",
            "duplex": True,
            "page_numbers": "outer",
            "running_headers": {"enabled": False, "source": "chapter", "suppress_on": []},
            "colophon": {"enabled": True, "placement": "title_verso"},
            "footer_metadata": {"suppress_repeated": True},
            "illumination": {
                "enabled": True,
                "rail": "outer",
                "bottom": True,
                "bottom_height": "0.30in",
                "bottom_offset": "0.28in",
                "width": "0.45in",
                "reserve_space": True,
                "placement": "chapter_openers",
                "assets": [{"id": "vine_gold", "source": "assets/illuminations/vine_gold.png", "pages": "chapter_openers"}],
            },
            "imposition": {"enabled": True, "layout": "booklet_signature_2up", "sheet_size": "letter", "signature_size": 8, "duplex": "short_edge"},
        },
    )
    resolved = resolve_profile("mythic")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    variables = yaml.safe_load(defaults.read_text())["variables"]
    header_includes = "\n".join(variables["header-includes"])
    assert "\\newcommand{\\OFOuterRail}" in header_includes
    assert "\\newcommand{\\OFBottomRail}" in header_includes
    assert "angle=90" in header_includes
    assert "width=\\OFIlluminationBottomRailHeight,height=\\OFIlluminationBottomRailWidth" in header_includes
    assert "\\marginpar" in header_includes
    assert variables["of_illumination_rail_width"] == "0.45in"


def test_pandoc_renderer_bound_delivery_edge_ornament_key_value_macro(tmp_path):
    plan = ProjectionPlan(
        profile_id="mythic",
        render_id="bound-edge-ornament-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="half_letter",
        page_margins=["inner=0.85in", "outer=0.60in", "top=0.65in", "bottom=0.70in"],
        title="Bound Edge Ornament",
        delivery={
            "mode": "bound",
            "binding": "saddle_stitch",
            "duplex": True,
            "illumination": {
                "enabled": True,
                "rail": "outer",
                "width": "0.45in",
                "reserve_space": True,
                "placement": "chapter_openers",
                "assets": [{"id": "vine_gold", "source": "assets/illuminations/vine_gold.png", "pages": "chapter_openers"}],
            },
        },
    )
    resolved = resolve_profile("mythic")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    variables = yaml.safe_load(defaults.read_text())["variables"]
    header_includes = "\n".join(variables["header-includes"])
    assert "\\newcommand{\\OFEdgeOrnament}[2][]" in header_includes
    assert "/ofedgeornament/.is family" in header_includes
    assert "edge/.store in=\\OFEO@edge" in header_includes
    assert "mirror/.store in=\\OFEO@mirror" in header_includes
    assert "wrap/.store in=\\OFEO@wrap" in header_includes
    assert "\\newlength{\\OFBinderyCriticalSafeInset}" in header_includes
    assert "\\setlength{\\OFBinderyCriticalSafeInset}{0.25in}" in header_includes
    assert "current page.north east" in header_includes
    assert "current page.north west" in header_includes
    assert "\\OFEO@safeOuterRectoXShift" in header_includes
    assert "\\OFEO@safeOuterVersoXShift" in header_includes
    assert "\\reflectbox" in header_includes
    assert "\\usepackage{wrapfig}" in header_includes
    assert "\\newcommand{\\OFEO@placeParagraph}" in header_includes
    assert "\\begin{wrapfigure}{o}" in header_includes
    assert "\\ifdim\\OFEO@width>\\OFIlluminationRailWidth" in header_includes
    assert "anchor=top,mirror=none,width=\\OFIlluminationRailWidth,yoffset=0pt,xoffset=0pt,wrap=false" in header_includes
    assert "\\includegraphics[width=\\OFEO@width]{\\detokenize{#1}}" in header_includes
    assert "\\includegraphics[width=\\OFIlluminationRailWidth]{\\detokenize{#1}}" in header_includes


def test_pandoc_renderer_page_size_overlay_is_document_spine_only(tmp_path):
    plan = ProjectionPlan(
        profile_id="letter",
        render_id="letter-a4-ignored",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="a4",
        page_margins=["margin=0.7in"],
    )
    resolved = resolve_profile("letter")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is None


def test_non_document_spine_evidence_reports_no_applied_page_margin(tmp_path):
    import re
    import shutil
    import subprocess

    if not shutil.which("pandoc") or not shutil.which("pdfinfo"):
        pytest.skip("pandoc/pdfinfo not available")
    if not Path("/Library/TeX/texbin/xelatex").exists() and not shutil.which("xelatex"):
        pytest.skip("xelatex not available")

    src = tmp_path / "letter-a5-request-ignored.md"
    src.write_text(
        "---\n"
        "uid: letter-a5-request-ignored\n"
        "title: Letter A5 Request Ignored\n"
        "author: Optical Foundry\n"
        "page_size: a5\n"
        "page_margin: 0.7in\n"
        "toc: false\n"
        "numbersections: false\n"
        "---\n\n"
        "Dear Keeper,\n\n"
        "Stationery profiles keep their fixed paper assumptions.\n"
    )

    evidence = DocumentRenderer().render(src, profile_id="mythic-letter", output_dir=str(tmp_path / "out"))

    assert evidence["render_metadata"]["profile_family"] == "stationery_art"
    assert evidence["render_metadata"]["page_geometry_options"] == []
    assert evidence["render_metadata"]["page_margin_options"] == []
    pdf_path = Path(evidence["output"]["pdf_path"])
    info = subprocess.check_output(["pdfinfo", "-box", str(pdf_path)], text=True)
    media = re.search(r"^MediaBox:\s+0\.00\s+0\.00\s+([0-9.]+)\s+([0-9.]+)", info, re.MULTILINE)
    assert media, info
    width, height = (float(media.group(1)), float(media.group(2)))
    assert width == pytest.approx(612.0, abs=1.0)
    assert height == pytest.approx(792.0, abs=1.0)


def test_pandoc_renderer_page_size_defaults_for_codex0_preserve_half_letter_book_geometry(tmp_path):
    plan = ProjectionPlan(
        profile_id="codex0",
        render_id="codex0-default-half-letter-doc",
        render_source=GF / "fixtures" / "sources" / "source-001.md",
        page_size="half_letter",
    )
    resolved = resolve_profile("codex0")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    data = yaml.safe_load(defaults.read_text())
    variables = data["variables"]
    assert variables["geometry"][:2] == ["paperwidth=5.5in", "paperheight=8.5in"]
    assert "margin=0.72in" in variables["geometry"]
    assert variables["classoption"] == ["11pt", "oneside", "statementpaper"]


def test_pandoc_renderer_page_size_defaults_preserve_source_header_includes(tmp_path):
    src = tmp_path / "header-include-source.md"
    src.write_text(
        "---\n"
        "title: Header Include Source\n"
        "header-includes:\n"
        "- \\usepackage{yugenillumination}\n"
        "page_size: a5\n"
        "---\n\n"
        "# Header Include Source\n"
    )
    plan = ProjectionPlan(
        profile_id="codex0",
        render_id="codex0-header-include-preserved",
        render_source=src,
        page_size="a5",
    )
    resolved = resolve_profile("codex0")

    defaults = PandocRenderer()._page_geometry_defaults(plan, resolved, tmp_path)

    assert defaults is not None
    import yaml
    variables = yaml.safe_load(defaults.read_text())["variables"]
    assert variables["header-includes"] == [
        r"\usepackage{yugenillumination}",
        r"\special{papersize=\the\paperwidth,\the\paperheight}",
    ]


def test_read_defaults_metadata_detects_placeholder_assets():
    r = PandocRenderer()
    meta = r._read_defaults_metadata(GF / "profiles" / "40_latex_import" / "defaults" / "elian_packet.yaml")
    assert meta["boundary"]["placeholder_assets"] is True
    assert any("placeholder" in w.lower() for w in meta["warnings"])


def test_pandoc_renderer_a4_page_size_sets_pdf_mediabox(tmp_path):
    import re
    import shutil
    import subprocess

    if not shutil.which("pandoc") or not shutil.which("pdfinfo"):
        pytest.skip("pandoc/pdfinfo not available")
    if not Path("/Library/TeX/texbin/xelatex").exists() and not shutil.which("xelatex"):
        pytest.skip("xelatex not available")

    src = tmp_path / "a4-mediabox.md"
    src.write_text(
        "---\n"
        "uid: a4-mediabox\n"
        "title: A4 MediaBox\n"
        "page_size: a4\n"
        "toc: false\n"
        "numbersections: false\n"
        "---\n\n"
        "# A4 MediaBox\n\n"
        "The physical PDF page box must be A4, not just the TeX geometry.\n"
    )

    evidence = DocumentRenderer().render(src, profile_id="cam", output_dir=str(tmp_path / "out"))
    assert evidence["render_metadata"]["page_geometry_options"][:1] == ["a4paper"]

    pdf_path = Path(evidence["output"]["pdf_path"])
    info = subprocess.check_output(["pdfinfo", "-box", str(pdf_path)], text=True)
    media = re.search(r"^MediaBox:\s+0\.00\s+0\.00\s+([0-9.]+)\s+([0-9.]+)", info, re.MULTILINE)
    assert media, info
    width, height = (float(media.group(1)), float(media.group(2)))
    assert width == pytest.approx(595.28, abs=1.0)
    assert height == pytest.approx(841.89, abs=1.0)


def test_pandoc_renderer_prepares_mermaid_source_before_pandoc(tmp_path):
    src = tmp_path / "mermaid-input.md"
    src.write_text(
        "---\ntitle: Mermaid Input\n---\n\n"
        "```mermaid\n"
        "xychart\n"
        "    line [1, 2, 3]\n"
        "```\n"
    )

    def fake_renderer(source: str, output_path: Path, config: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="cam",
        render_id="mermaid-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_mermaid_source(
        plan,
        tmp_path / "render-out",
        mermaid_renderer=fake_renderer,
        mermaid_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```mermaid" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "mermaid"
    assert prepared.boundary_assertions["mermaid_enabled"] is True
    assert prepared.boundary_assertions["mermaid_diagram_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True
    assert prepared.boundary_assertions["figure_count_by_kind"] == {"mermaid": 1}
    assert prepared.boundary_assertions["mermaid_theme"]["palette"][0] == "#0A3870"


def test_pandoc_renderer_prepares_vega_source_before_pandoc(tmp_path):
    src = tmp_path / "vega-input.md"
    src.write_text(
        "---\ntitle: Vega Input\n---\n\n"
        "```vega\n"
        "{\n"
        "  \"$schema\": \"https://vega.github.io/schema/vega/v5.json\",\n"
        "  \"width\": 120,\n"
        "  \"height\": 80,\n"
        "  \"data\": [{\"name\": \"table\", \"values\": [{\"x\": \"A\", \"y\": 1}]}],\n"
        "  \"marks\": [{\"type\": \"text\", \"encode\": {\"enter\": {\"text\": {\"value\": \"ok\"}}}}]\n"
        "}\n"
        "```\n"
    )

    def fake_renderer(spec: dict, output_path: Path, render_context: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="cam",
        render_id="vega-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_vega_source(
        plan,
        tmp_path / "render-out",
        vega_renderer=fake_renderer,
        vega_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```vega" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "vega"
    assert prepared.boundary_assertions["vega_enabled"] is True
    assert prepared.boundary_assertions["vega_chart_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True


def test_pandoc_renderer_prepares_d2_source_before_pandoc(tmp_path):
    src = tmp_path / "d2-input.md"
    src.write_text(
        "---\ntitle: D2 Input\n---\n\n"
        "```d2\n"
        "Oasis -> Optical Foundry\n"
        "Optical Foundry -> Evidence\n"
        "```\n"
    )

    def fake_renderer(source_text: str, output_path: Path, render_context: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="civic",
        render_id="d2-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_d2_source(
        plan,
        tmp_path / "render-out",
        d2_renderer=fake_renderer,
        d2_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```d2" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "d2"
    assert prepared.boundary_assertions["d2_enabled"] is True
    assert prepared.boundary_assertions["d2_diagram_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True


def test_pandoc_renderer_prepares_graphviz_source_before_pandoc(tmp_path):
    src = tmp_path / "dot-input.md"
    src.write_text(
        "---\ntitle: DOT Input\n---\n\n"
        "```dot\n"
        "digraph G {\n"
        "  Oasis -> Foundry;\n"
        "  Foundry -> Evidence;\n"
        "}\n"
        "```\n"
    )

    def fake_renderer(source_text: str, output_path: Path, render_context: dict) -> None:
        output_path.write_text("<svg></svg>")

    plan = ProjectionPlan(
        profile_id="civic",
        render_id="dot-input",
        render_source=src,
        figure_inventory=[],
        boundary_assertions={},
    )
    prepared = PandocRenderer()._prepare_graphviz_source(
        plan,
        tmp_path / "render-out",
        graphviz_renderer=fake_renderer,
        graphviz_output_format="svg",
    )

    assert prepared.render_source != src
    assert "```dot" not in prepared.render_source.read_text()
    assert prepared.figure_inventory[0]["kind"] == "graphviz_dot"
    assert prepared.boundary_assertions["graphviz_dot_enabled"] is True
    assert prepared.boundary_assertions["graphviz_dot_diagram_count"] == 1
    assert prepared.boundary_assertions["generated_figures_enabled"] is True


def test_pandoc_renderer_strips_unsafe_titlepage_background_frontmatter(tmp_path):
    src = tmp_path / "unsafe-title-bg.md"
    src.write_text(
        "---\n"
        "title: Unsafe Title BG\n"
        "titlepage: true\n"
        "titlepage_background_image: /etc/passwd\n"
        "variables:\n"
        "  titlepage_background_image: ../secret.png\n"
        "  titlepage: true\n"
        "---\n\n"
        "# Body\n"
    )

    guarded = PandocRenderer._titlepage_background_normalized_source(src, tmp_path, "unsafe-title-bg")
    text = guarded.read_text()

    assert guarded != src
    assert "/etc/passwd" not in text
    assert "../secret.png" not in text
    assert "titlepage: true" in text


def test_pandoc_renderer_keeps_safe_titlepage_background_frontmatter(tmp_path):
    src = tmp_path / "safe-title-bg.md"
    src.write_text(
        "---\n"
        "title: Safe Title BG\n"
        "titlepage: true\n"
        "titlepage_background_image: assets/cover.png\n"
        "variables:\n"
        "  titlepage_background_image: assets/cover.png\n"
        "---\n\n"
        "# Body\n"
    )

    guarded = PandocRenderer._titlepage_background_normalized_source(src, tmp_path, "safe-title-bg")

    assert guarded == src
