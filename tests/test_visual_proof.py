from __future__ import annotations

import json
from pathlib import Path

from engine.visual_proof import build_visual_proof, write_contact_sheet_svg


def _write_fake_png(path: Path) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_write_contact_sheet_svg_labels_pages_and_uses_relative_image_paths(tmp_path):
    page1 = tmp_path / "pages" / "proof-1.png"
    page2 = tmp_path / "pages" / "proof-2.png"
    page1.parent.mkdir()
    _write_fake_png(page1)
    _write_fake_png(page2)

    sheet = tmp_path / "proof" / "contact_sheet.svg"
    result = write_contact_sheet_svg(
        [page1, page2],
        output_svg=sheet,
        title="Optical Proof <Smoke>",
        columns=2,
        thumb_width=160,
    )

    assert result == sheet
    text = sheet.read_text(encoding="utf-8")
    assert "Optical Proof &lt;Smoke&gt;" in text
    assert "Page 1" in text
    assert "Page 2" in text
    assert "../pages/proof-1.png" in text
    assert "../pages/proof-2.png" in text


def test_build_visual_proof_writes_metadata_and_contact_sheet_with_injected_rasterizer(tmp_path):
    pdf = tmp_path / "artifact.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake proof input")

    def fake_rasterizer(pdf_path: Path, pages_dir: Path, *, max_pages: int, dpi: int) -> tuple[int, list[Path]]:
        assert pdf_path == pdf
        assert max_pages == 2
        assert dpi == 96
        p1 = pages_dir / "artifact-page-001.png"
        p2 = pages_dir / "artifact-page-002.png"
        pages_dir.mkdir(parents=True, exist_ok=True)
        _write_fake_png(p1)
        _write_fake_png(p2)
        return 5, [p1, p2]

    proof = build_visual_proof(
        pdf,
        output_dir=tmp_path / "proof",
        max_pages=2,
        columns=2,
        dpi=96,
        rasterizer=fake_rasterizer,
    )

    assert proof["status"] == "ok"
    assert proof["source_pdf"] == str(pdf)
    assert proof["source_pdf_pages"] == 5
    assert proof["pages_rasterized"] == 2
    assert proof["contact_sheet_svg"].endswith("contact_sheet.svg")
    metadata_path = Path(proof["metadata_path"])
    assert metadata_path.exists()
    on_disk = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert on_disk["page_images"] == proof["page_images"]
    assert Path(proof["contact_sheet_svg"]).exists()


def _proof_pdf(path, texts):
    import fitz

    doc = fitz.open()
    for t in texts:
        doc.new_page(width=396, height=612).insert_text((72, 300), t, fontsize=40)
    doc.save(str(path))
    doc.close()
    return path


def test_compare_contact_sheets_identical(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    from engine.visual_proof import compare_contact_sheets

    a = _proof_pdf(tmp_path / "a.pdf", ["one", "two", "three"])
    b = _proof_pdf(tmp_path / "b.pdf", ["one", "two", "three"])
    result = compare_contact_sheets(a, b, output_dir=tmp_path / "out", label="vol")
    assert result["identical"] is True
    assert result["differing_pages"] == []
    assert (tmp_path / "out" / "vol_baseline.png").exists()
    assert (tmp_path / "out" / "vol_candidate.png").exists()
    assert "diff_sheet" not in result


def test_compare_contact_sheets_marks_the_changed_page(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    from engine.visual_proof import compare_contact_sheets

    a = _proof_pdf(tmp_path / "a.pdf", ["one", "two", "three"])
    b = _proof_pdf(tmp_path / "b.pdf", ["one", "TWO", "three"])
    result = compare_contact_sheets(a, b, output_dir=tmp_path / "out", label="vol")
    assert result["identical"] is False
    assert result["differing_pages"] == [2]
    assert (tmp_path / "out" / "vol_diff.png").exists()


def test_compare_contact_sheets_page_count_mismatch(tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    from engine.visual_proof import compare_contact_sheets

    result = compare_contact_sheets(
        _proof_pdf(tmp_path / "a.pdf", ["one"]), _proof_pdf(tmp_path / "b.pdf", ["one", "two"]),
        output_dir=tmp_path / "out", label="vol",
    )
    assert result["identical"] is False
    assert (result["baseline_pages"], result["candidate_pages"]) == (1, 2)


def _page_with(path, *, text="words", pixel=(10, 20, 30), rule_y=500):
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=396, height=612)
    page.insert_text((72, 100), text, fontsize=20)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), 0)
    pix.set_rect(pix.irect, pixel)
    page.insert_image(fitz.Rect(100, 200, 200, 300), pixmap=pix)
    page.draw_line((72, rule_y), (300, rule_y))
    doc.save(str(path))
    doc.close()
    return path


def test_edge_only_requires_identical_content(tmp_path):
    __import__("pytest").importorskip("fitz")
    from engine.visual_proof import edge_only_pages

    base = _page_with(tmp_path / "base.pdf")
    assert edge_only_pages(base, _page_with(tmp_path / "same.pdf"), [1]) == [1]
    assert edge_only_pages(base, _page_with(tmp_path / "img.pdf", pixel=(10, 20, 31)), [1]) == []
    assert edge_only_pages(base, _page_with(tmp_path / "txt.pdf", text="other"), [1]) == []
    assert edge_only_pages(base, _page_with(tmp_path / "rule.pdf", rule_y=501), [1]) == []
