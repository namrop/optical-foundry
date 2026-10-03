"""E2 — bindery gates promoted from Codex 0 (promotion map E2)."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from engine.bindery import BinderyError, folio_run_report, press_sheet_map, punch_guide_svg, sewing_stations

fitz = pytest.importorskip("fitz")
ROOT = Path(__file__).resolve().parents[1]


def _pdf(path: Path, pages: int, labels: list[dict]) -> Path:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=396, height=612)
    doc.set_page_labels(labels)
    doc.save(str(path))
    return path


def test_a_run_seated_on_matching_parity_passes(tmp_path):
    # two unlabelled title pages, then folios 3.. on physical 3..
    pdf = _pdf(tmp_path / "ok.pdf", 8, [{"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 3}])
    rep = folio_run_report(pdf)
    assert rep["ok"] and rep["run"] == ["3", "8"] and rep["first_numbered_page"] == 3


def test_parity_skew_is_caught(tmp_path):
    pdf = _pdf(tmp_path / "skew.pdf", 6, [{"startpage": 1, "prefix": "", "style": "D", "firstpagenum": 207}])
    rep = folio_run_report(pdf)
    assert not rep["ok"] and "parity disagrees" in rep["problems"][0]


def test_roman_and_a_reseat_are_caught(tmp_path):
    roman = _pdf(tmp_path / "roman.pdf", 4, [{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1}])
    assert "non-arabic" in folio_run_report(roman)["problems"][0]
    reseat = _pdf(tmp_path / "reseat.pdf", 6, [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 1},
                                               {"startpage": 4, "prefix": "", "style": "D", "firstpagenum": 1}])
    assert any("not continuous" in p for p in folio_run_report(reseat)["problems"])


def test_sheet_map_matches_codex0_positions_and_indexes_folios(tmp_path):
    pdf = _pdf(tmp_path / "bind.pdf", 64, [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 1}])
    data = press_sheet_map(pdf, 32, sheet_sets={"cover": [1, 20]})
    assert data["sheets"] == 16 and data["signatures"] == 2
    # Codex 0's rule, j = 1..8 within signature: front_left 34-2j, front_right 2j-1, back 2j / 33-2j
    for e in data["sheet_map"]:
        off, j = 32 * (e["signature"] - 1), e["j"]
        assert e["pages"]["front_left"]["page"] == off + 34 - 2 * j
        assert e["pages"]["front_right"]["page"] == off + 2 * j - 1
        assert e["pages"]["back_left"]["page"] == off + 2 * j
        assert e["pages"]["back_right"]["page"] == off + 33 - 2 * j
        assert e["imposed_faces"] == {"front": 2 * e["sheet"] - 1, "back": 2 * e["sheet"]}
    assert data["folio_to_sheet"]["1"] == {"page": 1, "sheet": 1, "position": "front_right"}
    assert data["sheet_map"][0]["cover"] is True
    assert "do not exist" in data["warnings"][0]


def test_sheet_map_wants_the_bind_pdf(tmp_path):
    pdf = _pdf(tmp_path / "plain.pdf", 30, [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 1}])
    with pytest.raises(BinderyError, match="bind PDF"):
        press_sheet_map(pdf, 32)


def test_sewing_stations_reproduce_the_codex0_six_station_guide():
    st = sewing_stations(fold_height_in=8.5, kettle_offset_in=0.375, tapes=2, tape_width_in=1.2)
    assert [round(s.from_head_in, 6) for s in st] == [0.375, 2.158333, 3.358333, 5.141667, 6.341667, 8.125]
    assert [s.role for s in st][0] == "kettle" and st[-1].role == "kettle"
    svg = punch_guide_svg(st, fold_height_in=8.5)
    assert 'width="1.5in" height="8.5in"' in svg and svg.count("<circle") == 6
    with pytest.raises(BinderyError):
        sewing_stations(fold_height_in=4, kettle_offset_in=0.375, tapes=4, tape_width_in=1.2)


def test_cli_folio_run_exit_codes(tmp_path):
    ok = _pdf(tmp_path / "ok.pdf", 4, [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 1}])
    bad = _pdf(tmp_path / "bad.pdf", 4, [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 2}])
    run = lambda p: subprocess.run([sys.executable, "-m", "cli", "bindery", "folio-run", str(p)],
                                   cwd=ROOT, capture_output=True, text=True).returncode
    assert run(ok) == 0 and run(bad) == 1
