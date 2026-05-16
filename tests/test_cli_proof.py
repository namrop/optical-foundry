from __future__ import annotations

import json
import sys
from pathlib import Path

import cli


def test_cli_proof_contact_sheet_dispatches_visual_proof_builder(tmp_path, monkeypatch, capsys):
    pdf = tmp_path / "artifact.pdf"
    pdf.write_bytes(b"%PDF fake")
    out = tmp_path / "proof"
    calls = []

    def fake_build_visual_proof(pdf_path: Path, *, output_dir: Path, max_pages: int, columns: int, dpi: int):
        calls.append((Path(pdf_path), Path(output_dir), max_pages, columns, dpi))
        return {
            "status": "ok",
            "source_pdf": str(pdf_path),
            "pages_rasterized": max_pages,
            "contact_sheet_svg": str(Path(output_dir) / "contact_sheet.svg"),
            "metadata_path": str(Path(output_dir) / "visual_proof.json"),
        }

    monkeypatch.setattr(cli, "build_visual_proof", fake_build_visual_proof, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "foundry",
            "proof",
            "contact-sheet",
            str(pdf),
            "--output",
            str(out),
            "--max-pages",
            "2",
            "--columns",
            "2",
            "--dpi",
            "96",
        ],
    )

    assert cli.main() == 0
    assert calls == [(pdf, out, 2, 2, 96)]
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["contact_sheet_svg"].endswith("contact_sheet.svg")


def test_cli_smoke_profiles_accepts_proof_options(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_run_profile_smoke_matrix(*, profiles, fixture, output_dir, create_proofs, proof_max_pages, proof_columns, proof_dpi):
        calls.append((profiles, fixture, output_dir, create_proofs, proof_max_pages, proof_columns, proof_dpi))
        return {"status": "passed", "profiles_passed": 1, "profiles_failed": 0, "results": []}

    monkeypatch.setattr(cli, "run_profile_smoke_matrix", fake_run_profile_smoke_matrix)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "foundry",
            "smoke",
            "profiles",
            "--profile",
            "generic-report",
            "--fixture",
            "basic",
            "--output",
            str(tmp_path),
            "--proof",
            "--proof-max-pages",
            "4",
            "--proof-columns",
            "2",
            "--proof-dpi",
            "96",
        ],
    )

    assert cli.main() == 0
    assert calls == [(["generic-report"], "basic", str(tmp_path), True, 4, 2, 96)]
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
