"""E4 — the duplex registration instrument and its readings (promotion map E4)."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from engine.duplex_registration import (DuplexError, Station, default_stations, instrument_tex,
                                        render_instrument, summarize)


def test_back_is_the_front_mirrored_in_x():
    tex = instrument_tex([Station("C1", 7.36, 7.52), Station("P1", 2.75, 6.02, cross=True)], width=11, height=8.5)
    assert "\\FrontH{7.36}{7.52}{C1}" in tex and "\\BackH{3.64}{7.52}{C1}" in tex
    assert "\\FrontCross{2.75}{6.02}{P1}" in tex and "\\BackCross{8.25}{6.02}{P1}" in tex
    assert "paperwidth=11in,paperheight=8.5in" in tex


def test_bad_stations_are_refused():
    with pytest.raises(DuplexError, match="off the sheet"):
        instrument_tex([Station("X", 0.2, 4)], width=11, height=8.5)
    with pytest.raises(DuplexError, match="label"):
        instrument_tex([Station("a b", 5, 4)], width=11, height=8.5)


@pytest.mark.skipif(not (shutil.which("lualatex") or shutil.which("xelatex")), reason="needs a TeX engine")
def test_instrument_compiles_to_two_sheet_sized_pages(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf = render_instrument(tmp_path / "inst.pdf", stations=default_stations(11, 8.5), width=11, height=8.5)
    with fitz.open(str(pdf)) as doc:
        assert doc.page_count == 2
        assert (round(doc[0].rect.width), round(doc[0].rect.height)) == (792, 612)
        # a front label sits at x, its back twin at 11in - x
        f = next(b for b in doc[0].get_text("words") if b[4] == "FL1")
        r = next(b for b in doc[1].get_text("words") if b[4] == "L1")
        assert abs(f[0] / 72 - 2.82) < 0.1 and abs(r[2] / 72 - (11 - 2.75 - 10 / 25.4 - 0.1)) < 0.15


def test_summary_reproduces_a_seat_from_readings():
    readings = [{"sheet": i, "station": s, "dx_mm": v}
                for i, (c1, c2) in enumerate([(1.80, 1.81), (1.79, 1.80), (1.81, 1.80)], start=1)
                for s, v in (("C1", c1), ("C2", c2))] + [{"sheet": 1, "station": "A1", "dx_mm": 2.4, "dy_mm": 0.3}]
    out = summarize(readings, deciding=["C1", "C2"])
    assert out["seat_mm"] == pytest.approx(1.8017, abs=1e-3) and out["dx"]["n"] == 6
    assert out["stations"]["A1"]["mean_mm"] == 2.4 and out["dy"]["n"] == 1 and out["sheets"] == 3
    with pytest.raises(DuplexError):
        summarize(readings, deciding=["Z9"])
