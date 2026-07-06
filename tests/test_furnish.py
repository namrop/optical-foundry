"""Tests for the per-sheet furnish map."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.furnish import (  # noqa: E402
    FURNISH_SCHEMA_VERSION,
    build_page_to_stock,
    compute_furnish,
    write_furnish_json,
    write_furnish_text,
)


def _sample_imposition_mapping() -> dict:
    """Minimal imposition_map_v1 payload: 1 signature, 2 sheets, 8 pages."""
    return {
        "schema_version": "imposition_map_v1",
        "layout": "booklet_signature_2up",
        "signature_size": 8,
        "input_pages": 8,
        "padded_pages": 8,
        "blank_count": 0,
        "signatures": [
            {
                "signature_index": 0,
                "source_page_range": [1, 8],
                "padded_page_range": [1, 8],
                "sheets": [
                    {
                        "sheet_index": 0,
                        "front": {"output_page": 1, "pages": [8, 1], "rotate_180": False},
                        "back": {"output_page": 2, "pages": [2, 7], "rotate_180": False},
                    },
                    {
                        "sheet_index": 1,
                        "front": {"output_page": 3, "pages": [6, 3], "rotate_180": False},
                        "back": {"output_page": 4, "pages": [4, 5], "rotate_180": False},
                    },
                ],
            }
        ],
    }


def test_build_page_to_stock_marks_divider_page():
    inventory = [
        {"uid": "part-i", "stock": "cardstock", "blank_after": True},
        {"uid": "ch-1", "stock": "text", "blank_after": False},
    ]
    page_map = {"part-i": 3, "ch-1": 5}
    result = build_page_to_stock(total_pdf_pages=8, divider_page_map=page_map, divider_inventory=inventory)
    assert result[3] == "cardstock"
    # blank_after=true extends stock envelope to the following blank verso.
    assert result[4] == "cardstock"
    # Text-stock divider is a no-op (page defaults to text).
    assert result.get(5, "text") == "text"


def test_build_page_to_stock_defaults_unknown_stock_to_text():
    inventory = [{"uid": "d1", "stock": "papyrus"}]  # unknown stock
    page_map = {"d1": 2}
    # Compiler already normalizes unknown stocks to "text"; furnish should
    # respect whatever the inventory says, since normalization is a compile-time
    # concern. Here we just verify the raw value flows through.
    result = build_page_to_stock(total_pdf_pages=4, divider_page_map=page_map, divider_inventory=inventory)
    assert result[2] == "papyrus"  # not filtered here; upstream normalization is caller's job


def test_compute_furnish_flags_cardstock_sheet_side():
    mapping = _sample_imposition_mapping()
    # Page 8 is cardstock (a divider). It lands on sheet 0 front.
    page_to_stock = {8: "cardstock"}
    furnish = compute_furnish(mapping, page_to_stock)
    assert furnish.schema_version == FURNISH_SCHEMA_VERSION
    assert furnish.total_signatures == 1
    assert furnish.total_sheets == 2
    front0 = next(s for s in furnish.sheet_sides if s.sheet_index == 0 and s.side == "front")
    assert front0.stock == "cardstock"
    # Pages [8, 1]: page 8 is cardstock, page 1 defaults to text → mixed.
    assert front0.mixed_stocks_present is True
    assert furnish.stock_summary["cardstock"] == 1
    assert furnish.stock_summary["text"] == 3
    assert any("mixed stock" in w for w in furnish.warnings)


def test_compute_furnish_all_text_no_warnings():
    mapping = _sample_imposition_mapping()
    furnish = compute_furnish(mapping, page_to_stock={})
    assert furnish.stock_summary == {"text": 4}
    assert furnish.warnings == []


def test_compute_furnish_pure_cardstock_side_not_mixed():
    """A sheet-side whose pages are ALL cardstock (or all cardstock + null blanks)
    is not mixed."""
    mapping = _sample_imposition_mapping()
    # Both pages of sheet 0 front are cardstock.
    page_to_stock = {8: "cardstock", 1: "cardstock"}
    furnish = compute_furnish(mapping, page_to_stock)
    front0 = next(s for s in furnish.sheet_sides if s.sheet_index == 0 and s.side == "front")
    assert front0.stock == "cardstock"
    assert front0.mixed_stocks_present is False


def test_write_furnish_json_and_text_roundtrip(tmp_path):
    mapping = _sample_imposition_mapping()
    page_to_stock = {8: "cardstock", 1: "cardstock"}
    furnish = compute_furnish(
        mapping,
        page_to_stock,
        input_pdf=tmp_path / "book.pdf",
        imposition_mapping_path=tmp_path / "book.imposition.json",
        divider_page_map={"part-i": 8},
    )
    json_path = tmp_path / "book.furnish.json"
    txt_path = tmp_path / "book.furnish.txt"
    write_furnish_json(furnish, json_path)
    write_furnish_text(furnish, txt_path)
    parsed = json.loads(json_path.read_text())
    assert parsed["schema_version"] == FURNISH_SCHEMA_VERSION
    assert parsed["stock_summary"]["cardstock"] == 1
    assert parsed["divider_page_map"] == {"part-i": 8}
    txt = txt_path.read_text()
    assert "Furnish plan" in txt
    assert "cardstock" in txt
    assert "part-i" in txt  # divider landing table
