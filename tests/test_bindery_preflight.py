from __future__ import annotations

from pathlib import Path

from engine.bindery_preflight import build_bindery_preflight_report, compute_safe_area_layout, write_safe_area_guide_tex
from engine.projection_plan import ProjectionPlan


PDFINFO_SINGLE_NO_BLEED = """
Pages:           32
Encrypted:       no
Page size:       396 x 612 pts
MediaBox:            0.00     0.00   396.00   612.00
CropBox:             0.00     0.00   396.00   612.00
BleedBox:            0.00     0.00   396.00   612.00
TrimBox:             0.00     0.00   396.00   612.00
ArtBox:              0.00     0.00   396.00   612.00
PDF version:     1.5
"""

PDFFONTS_EMBEDDED = """
name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
XXDBAR+TimesNewRomanPS-BoldMT        CID TrueType      Identity-H       yes yes yes      5  0
RQMDKX+TimesNewRomanPSMT             CID TrueType      Identity-H       yes yes yes     10  0
"""

PDFIMAGES_MIXED = """
page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio
--------------------------------------------------------------------------------------------
   1     0 image     825  1275  rgb     3   8  image  no         9  0   357   357 2138K  69%
   9     9 image     825  1275  rgb     3   8  image  no        45  0   255   255 2288K  74%
  12    14 image     768   512  cmyk    4   8  image  no        58  0   226   226  878K  76%
"""


def test_bindery_preflight_report_classifies_single_page_pdf_as_prototype_not_press_ready(tmp_path):
    report = build_bindery_preflight_report(
        pdf_path=tmp_path / "book.pdf",
        pdfinfo_text=PDFINFO_SINGLE_NO_BLEED,
        pdffonts_text=PDFFONTS_EMBEDDED,
        pdfimages_text=PDFIMAGES_MIXED,
        page_size="half_letter",
        page_margins=["inner=0.85in", "outer=0.60in", "top=0.65in", "bottom=0.70in"],
        delivery={"mode": "bound", "binding": "saddle_stitch"},
        imposition={"status": "ok", "output_pdf": "/tmp/imposed.pdf"},
        safe_area_guide=None,
    )

    assert report["recommendation"]["send_default"] == "single_page_pdf"
    assert report["readiness"]["prototype_ready"] is True
    assert report["readiness"]["vendor_independent_press_ready"] is False
    assert "no_bleed" in report["readiness"]["blocking_press_ready_issues"]
    assert "rgb_images_present" in report["readiness"]["blocking_press_ready_issues"]
    assert "images_below_300ppi" in report["readiness"]["blocking_press_ready_issues"]
    assert report["fonts"]["all_embedded"] is True
    assert report["images"]["min_effective_ppi"] == 226
    assert report["page_boxes"]["trim_inches"] == {"width": 5.5, "height": 8.5}


def test_safe_area_layout_clamps_all_guide_boxes_inside_trim(tmp_path):
    plan = _bound_rail_plan(tmp_path)

    layout = compute_safe_area_layout(plan, deckle_zone="0.20in", critical_safe_inset="0.25in")

    assert layout["trim_inches"] == {"width": 5.5, "height": 8.5}
    assert layout["body_box_inches"]["recto"] == {"x": 0.85, "y": 0.65, "width": 4.05, "height": 7.15}
    assert layout["rail_box_inches"]["recto"] == {"x": 4.95, "y": 0.65, "width": 0.45, "height": 7.15}
    for group in ("body_box_inches", "rail_box_inches", "deckle_box_inches", "critical_safe_box_inches"):
        for side, box in layout[group].items():
            assert box["x"] >= 0, (group, side, box)
            assert box["y"] >= 0, (group, side, box)
            assert box["x"] + box["width"] <= layout["trim_inches"]["width"], (group, side, box)
            assert box["y"] + box["height"] <= layout["trim_inches"]["height"], (group, side, box)


def test_safe_area_guide_tex_records_trim_deckle_rail_and_body_boxes(tmp_path):
    plan = _bound_rail_plan(tmp_path)

    guide = write_safe_area_guide_tex(plan, tmp_path, deckle_zone="0.20in", critical_safe_inset="0.25in")

    tex = Path(guide["tex_path"])
    assert tex.exists()
    assert guide["trim_inches"] == {"width": 5.5, "height": 8.5}
    assert guide["body_box_inches"]["recto"] == {"x": 0.85, "y": 0.65, "width": 4.05, "height": 7.15}
    assert guide["rail_box_inches"]["recto"] == {"x": 4.95, "y": 0.65, "width": 0.45, "height": 7.15}
    body = tex.read_text()
    assert "\\clip (0,0) rectangle (5.500,8.500);" in body
    assert "Deckle / sacrificial zone" in body
    assert "Critical-safe inset" in body
    assert "Outer illumination rail" in body


def test_safe_area_guide_can_overlay_boxes_on_source_pdf(tmp_path):
    plan = _bound_rail_plan(tmp_path)
    source_pdf = tmp_path / "single-page.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n% placeholder for tex source path test\n")

    guide = write_safe_area_guide_tex(
        plan,
        tmp_path,
        deckle_zone="0.20in",
        critical_safe_inset="0.25in",
        overlay_pdf_path=source_pdf,
        overlay_page_count=3,
    )

    overlay_tex = Path(guide["overlay_tex_path"])
    assert overlay_tex.exists()
    assert guide["overlay_pdf_path"].endswith(".safe_area_overlay.pdf")
    body = overlay_tex.read_text()
    assert "remember picture,overlay" in body
    assert "current page.south west" in body
    assert "\\includepdf[pages={1},fitpaper=true,pagecommand={\\OFRectoOverlay}]" in body
    assert "\\includepdf[pages={2},fitpaper=true,pagecommand={\\OFVersoOverlay}]" in body
    assert "\\includepdf[pages={3},fitpaper=true,pagecommand={\\OFRectoOverlay}]" in body


def _bound_rail_plan(tmp_path: Path) -> ProjectionPlan:
    return ProjectionPlan(
        profile_id="mythic",
        render_id="safe-area-proof",
        render_source=tmp_path / "source.md",
        page_size="half_letter",
        page_margins=["inner=0.85in", "outer=0.60in", "top=0.65in", "bottom=0.70in"],
        delivery={
            "mode": "bound",
            "duplex": True,
            "illumination": {"enabled": True, "width": "0.45in", "rail": "outer", "reserve_space": True},
        },
    )
