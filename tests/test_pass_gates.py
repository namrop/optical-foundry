from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from engine.pass_gates import compare_renders


def _pdf(path: Path, pages: int, *, labels_start: int = 1, outline_page: int = 2, outline_y: float = 100) -> Path:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page(width=396, height=612).insert_text((72, 72), f"page {i + 1}")
    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": labels_start}])
    doc.set_toc([[1, "Chapter", outline_page, {"kind": fitz.LINK_GOTO, "page": outline_page - 1, "to": fitz.Point(0, outline_y)}]])
    doc.save(str(path))
    doc.close()
    return path


def test_same_shape_has_no_differences(tmp_path):
    assert compare_renders(_pdf(tmp_path / "a.pdf", 4), _pdf(tmp_path / "b.pdf", 4)) == []


def test_page_count_difference(tmp_path):
    assert compare_renders(_pdf(tmp_path / "a.pdf", 4), _pdf(tmp_path / "b.pdf", 6)) == ["page count 4 != 6"]


def test_label_difference_names_the_page(tmp_path):
    diffs = compare_renders(_pdf(tmp_path / "a.pdf", 3), _pdf(tmp_path / "b.pdf", 3, labels_start=207))
    assert diffs[0] == "page 1: label '1' != '207'"


def test_outline_difference(tmp_path):
    diffs = compare_renders(_pdf(tmp_path / "a.pdf", 3), _pdf(tmp_path / "b.pdf", 3, outline_page=3))
    assert diffs and diffs[0].startswith("outline entry 1:")
