"""Tests for signature/booklet PDF imposition."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.imposition import (  # noqa: E402
    ImpositionError,
    _validate_pdf_page_size,
    build_booklet_signature_plan,
    impose_pdf,
)


def test_booklet_signature_plan_maps_eight_pages_to_two_duplex_sheets():
    plan = build_booklet_signature_plan(total_pages=8, signature_size=8)

    assert plan.input_pages == 8
    assert plan.padded_pages == 8
    assert plan.blank_count == 0
    assert len(plan.signatures) == 1
    sheets = plan.signatures[0].sheets
    assert [side.pages for sheet in sheets for side in sheet.sides] == [
        [8, 1],
        [2, 7],
        [6, 3],
        [4, 5],
    ]


def test_booklet_signature_plan_pads_final_signature_with_blanks():
    plan = build_booklet_signature_plan(total_pages=5, signature_size=8)

    assert plan.padded_pages == 8
    assert plan.blank_count == 3
    sheets = plan.signatures[0].sheets
    assert [side.pages for sheet in sheets for side in sheet.sides] == [
        [None, 1],
        [2, None],
        [None, 3],
        [4, 5],
    ]


def test_booklet_signature_plan_rejects_non_folio_signature_size():
    with pytest.raises(ImpositionError, match="multiple of 4"):
        build_booklet_signature_plan(total_pages=8, signature_size=6)


def test_pdf_page_size_validation_rejects_nonmatching_later_pages():
    pdf_info = {
        "pages": 2,
        "width_pt": 396.0,
        "height_pt": 612.0,
        "page_sizes": [
            {"page": 1, "width_pt": 396.0, "height_pt": 612.0},
            {"page": 2, "width_pt": 612.0, "height_pt": 792.0},
        ],
    }

    with pytest.raises(ImpositionError, match="p2=8.50×11.00in"):
        _validate_pdf_page_size(pdf_info, "half_letter", context="input PDF")


def test_impose_pdf_generates_letter_landscape_sides_and_mapping(tmp_path):
    if not shutil.which("pdfinfo") or not Path("/Library/TeX/texbin/xelatex").exists():
        pytest.skip("pdfinfo/xelatex unavailable")

    source_pdf = _make_half_letter_source_pdf(tmp_path, pages=8)
    result = impose_pdf(
        source_pdf,
        output=tmp_path / "imposed",
        page_size="half_letter",
        sheet_size="letter",
        signature_size=8,
        duplex_mode="short-edge",
    )

    assert result.output_pdf.exists()
    assert result.mapping_json.exists()
    mapping = json.loads(result.mapping_json.read_text())
    assert mapping["page_size"] == "half_letter"
    assert mapping["sheet_size"] == "letter"
    assert mapping["signature_size"] == 8
    assert mapping["duplex_mode"] == "short_edge"
    assert mapping["input_pages"] == 8
    assert mapping["padded_pages"] == 8
    assert mapping["signatures"][0]["sheets"][0]["front"]["pages"] == [8, 1]
    assert mapping["signatures"][0]["sheets"][0]["back"]["pages"] == [2, 7]

    info = subprocess.check_output(["pdfinfo", "-box", str(result.output_pdf)], text=True)
    pages_match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
    assert pages_match and int(pages_match.group(1)) == 4
    size_match = re.search(r"^Page size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts", info, re.MULTILINE)
    assert size_match, info
    width, height = float(size_match.group(1)), float(size_match.group(2))
    assert width == pytest.approx(792.0, abs=1.0)
    assert height == pytest.approx(612.0, abs=1.0)


def test_cli_impose_accepts_requested_print_parameters(tmp_path):
    if not shutil.which("pdfinfo") or not Path("/Library/TeX/texbin/xelatex").exists():
        pytest.skip("pdfinfo/xelatex unavailable")

    source_pdf = _make_half_letter_source_pdf(tmp_path, pages=4)
    out_dir = tmp_path / "cli-out"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli",
            "impose",
            str(source_pdf),
            "--output",
            str(out_dir),
            "--page-size",
            "half-letter",
            "--sheet-size",
            "letter",
            "--signature-size",
            "4",
            "--duplex",
            "short-edge",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"
    assert payload["page_size"] == "half_letter"
    assert payload["sheet_size"] == "letter"
    assert payload["signature_size"] == 4
    assert payload["duplex_mode"] == "short_edge"
    assert Path(payload["output"]).exists()
    assert Path(payload["mapping"]).exists()


def _make_half_letter_source_pdf(tmp_path: Path, *, pages: int) -> Path:
    tex = tmp_path / "source.tex"
    body = "\n".join(
        rf"\noindent\Huge Page {idx}\newpage" for idx in range(1, pages + 1)
    )
    tex.write_text(
        r"""
\documentclass[11pt]{article}
\usepackage[paperwidth=5.5in,paperheight=8.5in,margin=0.4in]{geometry}
\pagestyle{empty}
\begin{document}
""".lstrip()
        + body
        + "\n" + r"\end{document}" + "\n"
    )
    subprocess.run(
        ["/Library/TeX/texbin/xelatex", "-interaction=nonstopmode", "-halt-on-error", tex.name],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )
    return tex.with_suffix(".pdf")
