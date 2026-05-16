from __future__ import annotations

import json
from pathlib import Path

from engine.profile_smoke import (
    DEFAULT_DOCUMENT_SMOKE_PROFILES,
    build_smoke_source,
    run_profile_smoke_matrix,
)


class FakeRenderer:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[tuple[Path, str, str]] = []

    def render(self, source: Path, profile_id: str, output_dir: str | None = None) -> dict:
        self.calls.append((source, profile_id, output_dir or ""))
        if profile_id in self.failures:
            return {
                "status": "error",
                "warnings": ["synthetic failure"],
                "output": {"pdf_path": "unknown", "pdf_pages": 0},
                "boundary": {"target_40_latex_mutated": False},
            }
        return {
            "status": "ok",
            "warnings": [],
            "output": {"pdf_path": f"{output_dir}/{profile_id}.pdf", "pdf_pages": 1},
            "boundary": {"target_40_latex_mutated": False},
        }


def test_build_illuminated_initial_fixture_uses_profile_owned_dropcap_asset():
    source = build_smoke_source("illuminated-initial", title="Fixture")

    assert "```of-initial" in source
    assert "path: assets/dropcaps/oasis/T.png" in source
    assert "align: bottom" in source
    assert "Optical Foundry smoke marker" in source


def test_profile_smoke_matrix_records_success_failure_and_writes_summary(tmp_path):
    renderer = FakeRenderer(failures={"cam"})

    summary = run_profile_smoke_matrix(
        profiles=["mythic", "cam"],
        fixture="basic",
        output_dir=tmp_path,
        renderer=renderer,
    )

    assert summary["status"] == "failed"
    assert summary["profiles_requested"] == 2
    assert summary["profiles_passed"] == 1
    assert summary["profiles_failed"] == 1
    assert [entry["profile"] for entry in summary["results"]] == ["mythic", "cam"]
    assert summary["results"][0]["status"] == "passed"
    assert summary["results"][0]["target_40_latex_mutated"] is False
    assert summary["results"][1]["status"] == "failed"
    assert "synthetic failure" in summary["results"][1]["warnings"]

    summary_path = tmp_path / "profile_smoke_summary.json"
    assert summary_path.exists()
    assert json.loads(summary_path.read_text())["profiles_failed"] == 1
    assert (tmp_path / "profile_smoke_basic.md").exists()
    assert renderer.calls[0][1] == "mythic"
    assert renderer.calls[0][2].endswith("mythic")


def test_default_document_smoke_profiles_cover_document_spine_and_stationery_profiles():
    assert "cam" in DEFAULT_DOCUMENT_SMOKE_PROFILES
    assert "codex0" in DEFAULT_DOCUMENT_SMOKE_PROFILES
    assert "mythic-letter-johannah" in DEFAULT_DOCUMENT_SMOKE_PROFILES
    assert "sticker-sheet" not in DEFAULT_DOCUMENT_SMOKE_PROFILES
