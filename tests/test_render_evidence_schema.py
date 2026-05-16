from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_render_evidence_schema_declares_status_and_validation_surface():
    schema = yaml.safe_load((ROOT / "schemas" / "render_evidence_v1.yaml").read_text(encoding="utf-8"))
    props = schema["properties"]

    assert props["status"]["enum"] == ["ok", "error"]
    validation = props["validation"]["properties"]
    assert validation["status"]["enum"] == ["passed", "failed"]
    assert "pdf_written" in validation["checks"]["properties"]
    assert "raw_latex_leakage" in validation["checks"]["properties"]
    assert validation["warning_count"]["type"] == "integer"
