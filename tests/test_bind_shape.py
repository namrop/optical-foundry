from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from engine.bind_shape import BindShapeError, bind_output_path, pad_to_signature, signature_pad


def _pdf(path: Path, pages: int) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=396, height=612)  # 5.5 x 8.5 in
        page.insert_text((72, 72), f"page {i + 1}")
    doc.save(str(path))
    doc.close()
    return path


def _mark(path: Path) -> Path:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 80), 0)
    pix.clear_with(0)
    pix.save(str(path))
    return path


def test_signature_pad_arithmetic():
    assert signature_pad(224, 32) == 0
    assert signature_pad(222, 32) == 2
    assert signature_pad(2, 16) == 14


def test_odd_page_count_is_refused_not_padded():
    with pytest.raises(BindShapeError, match="ODD"):
        signature_pad(285, 32)


def test_signature_size_must_be_multiple_of_four():
    with pytest.raises(BindShapeError):
        signature_pad(10, 6)


def test_pad_writes_bind_twin_to_whole_signature(tmp_path):
    src = _pdf(tmp_path / "vol.pdf", 10)
    result = pad_to_signature(src, 16)
    assert result.output == bind_output_path(src) == tmp_path / "vol_bind.pdf"
    assert (result.rendered_pages, result.pad_pages, result.total_pages, result.signatures) == (10, 6, 16, 1)
    out = fitz.open(str(result.output))
    assert out.page_count == 16
    assert out[15].rect == out[9].rect
    assert out[15].get_images() == []
    # The reading artifact is untouched.
    assert fitz.open(str(src)).page_count == 10


def test_pad_leaves_carry_the_mark_centred_at_width_fraction(tmp_path):
    src = _pdf(tmp_path / "vol.pdf", 4)
    mark = _mark(tmp_path / "mark.png")
    result = pad_to_signature(src, 8, blank_mark=mark, mark_width_fraction=0.25)
    out = fitz.open(str(result.output))
    for index in range(4, 8):
        page = out[index]
        (info,) = page.get_image_info()
        bbox = fitz.Rect(info["bbox"])
        assert bbox.width == pytest.approx(page.rect.width * 0.25, abs=0.01)
        assert bbox.height == pytest.approx(bbox.width * 2, abs=0.01)  # 40 x 80 aspect
        assert (bbox.x0 + bbox.x1) / 2 == pytest.approx(page.rect.width / 2, abs=0.01)
    assert out[3].get_images() == []


def test_exact_signature_writes_unpadded_twin(tmp_path):
    src = _pdf(tmp_path / "vol.pdf", 8)
    result = pad_to_signature(src, 8)
    assert result.pad_pages == 0
    assert fitz.open(str(result.output)).page_count == 8


def test_missing_mark_is_an_error(tmp_path):
    src = _pdf(tmp_path / "vol.pdf", 2)
    with pytest.raises(BindShapeError, match="mark not found"):
        pad_to_signature(src, 4, blank_mark=tmp_path / "absent.png")
