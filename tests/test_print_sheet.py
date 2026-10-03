"""E3 — print sheets with non-uniform placements (promotion map E3)."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from engine.print_sheet import PrintSheetError, plan, render

fitz = pytest.importorskip("fitz")
Image = pytest.importorskip("PIL.Image")
ROOT = Path(__file__).resolve().parents[1]


def _img(path: Path, w: int, h: int, top=(255, 0, 0)) -> Path:
    im = Image.new("RGB", (w, h), (255, 255, 255))
    for x in range(w):
        for y in range(max(1, h // 10)):
            im.putpixel((x, y), top)   # a coloured band along the image's top edge
    im.save(path)
    return path


def _sheet(tmp: Path, items, **extra) -> Path:
    m = {"kind": "print_sheet", "schema_version": "print_sheet_v1", "sheet_id": "labels",
         "page": {"size": "letter"}, "items": items, **extra}
    p = tmp / "sheet.yaml"
    p.write_text(yaml.safe_dump(m), encoding="utf-8")
    return p


def test_cover_plus_rotated_spine_labels_place_exactly(tmp_path):
    _img(tmp_path / "cover.png", 900, 1680)        # 3 x 5.6 in at 300 dpi
    _img(tmp_path / "spine.png", 2100, 150)        # 7 x 0.5 in
    _img(tmp_path / "spine_small.png", 1050, 75)   # 3.5 x 0.25 in, set sideways
    items = [
        {"id": "cover", "image": "cover.png", "x": "0.5in", "y": "1in", "width": "3in", "height": "5.6in",
         "copies": [{"x": "3.75in", "y": "1in"}]},
        {"id": "spine", "image": "spine.png", "x": "0.5in", "y": "7in", "width": "7in", "height": "0.5in"},
        {"id": "spine-turned", "image": "spine_small.png", "x": "7.5in", "y": "1in", "width": "0.25in",
         "height": "3.5in", "rotate": 90},
    ]
    ev = render(_sheet(tmp_path, items), tmp_path / "out")
    assert ev["status"] == "ok" and [i["id"] for i in ev["items"]] == ["cover", "cover#2", "spine", "spine-turned"]
    assert ev["items"][0]["dpi"] == pytest.approx(300, abs=1)
    with fitz.open(ev["output"]) as doc:
        page = doc[0]
        assert (page.rect.width, page.rect.height) == (612, 792)
        boxes = {(round(i["bbox"][0] / 72, 3), round(i["bbox"][1] / 72, 3)) for i in page.get_image_info()}
        assert {(0.5, 1.0), (3.75, 1.0), (0.5, 7.0), (7.5, 1.0)} <= boxes
        # rotate: 90 is clockwise: the art's top band ends up on the box's RIGHT edge
        pix = page.get_pixmap(dpi=144, clip=fitz.Rect(7.5 * 72, 1 * 72, 7.75 * 72, 4.5 * 72))
        right = pix.pixel(pix.width - 2, pix.height // 2)
        left = pix.pixel(1, pix.height // 2)
        assert right[0] > 200 and right[1] < 80 and left == (255, 255, 255)


def test_off_page_and_overlap_are_refused(tmp_path):
    _img(tmp_path / "a.png", 300, 300)
    m = yaml.safe_load(_sheet(tmp_path, [
        {"id": "a", "image": "a.png", "x": "8in", "y": "1in", "width": "1in", "height": "1in"},
        {"id": "b", "image": "a.png", "x": "1in", "y": "1in", "width": "1in", "height": "1in"},
        {"id": "c", "image": "a.png", "x": "1.5in", "y": "1.5in", "width": "1in", "height": "1in"},
    ]).read_text())
    with pytest.raises(PrintSheetError) as exc:
        plan(m, base=tmp_path)
    assert "a: box (with its cut marks) runs off the page" in str(exc.value)
    assert "b and c overlap" in str(exc.value)


def test_stretching_and_low_resolution_are_refused(tmp_path):
    _img(tmp_path / "sq.png", 600, 600)
    m = yaml.safe_load(_sheet(tmp_path, [{"image": "sq.png", "x": "1in", "y": "1in", "width": "4in", "height": "2in"}]).read_text())
    with pytest.raises(PrintSheetError, match="aspect"):
        plan(m, base=tmp_path)
    m["items"][0]["height"] = "4in"
    with pytest.raises(PrintSheetError, match="150 dpi"):
        plan(m, base=tmp_path)


def test_cli_exit_codes(tmp_path):
    _img(tmp_path / "a.png", 300, 300)
    good = _sheet(tmp_path, [{"image": "a.png", "x": "1in", "y": "1in", "width": "1in", "height": "1in"}])
    rc = subprocess.run([sys.executable, "-m", "cli", "print-sheet", str(good), "--output", str(tmp_path / "o")],
                        cwd=ROOT, capture_output=True, text=True).returncode
    assert rc == 0 and (tmp_path / "o" / "labels.pdf").is_file()
