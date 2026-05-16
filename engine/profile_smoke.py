"""Reusable profile smoke matrix helpers for Optical Foundry.

The smoke matrix renders one generated Markdown fixture across a bounded profile
set and writes a machine-readable summary. It is intentionally separate from
profile capability checking: the checker reports static capability; this module
proves that selected profiles actually render a representative document.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from renderers.document_renderer import DocumentRenderer
from engine.visual_proof import build_visual_proof


DEFAULT_DOCUMENT_SMOKE_PROFILES: tuple[str, ...] = (
    "cam",
    "codex0",
    "convergence",
    "creative",
    "generic-report",
    "keeper",
    "letter",
    "life",
    "mythic",
    "mythic-letter",
    "mythic-letter-johannah",
    "prometheus-packet",
    "risk",
    "tech",
    "yugen-brand",
    "yugen-brand-elevated",
    "yugen-civic",
)


class ProfileSmokeRenderer(Protocol):
    def render(self, source: Path, profile_id: str, output_dir: str | None = None) -> dict[str, Any]:
        ...


def build_smoke_source(fixture: str, *, title: str = "Optical Foundry Profile Smoke") -> str:
    """Return generated Markdown source for a named profile smoke fixture."""

    base_frontmatter = f"""---
title: "{title}"
author: "Optical Foundry"
toc: false
numbersections: false
---
"""
    body = """
# Profile Smoke

Optical Foundry smoke marker: this sentence must remain live text in every
successful PDF render.

This paragraph is intentionally ordinary prose. It exercises the profile's
normal document flow without depending on packet-specific source material.
""".lstrip()

    if fixture == "basic":
        return base_frontmatter + "\n" + body

    if fixture == "illuminated-initial":
        initial = """```of-initial
path: assets/dropcaps/oasis/T.png
width: .84in
lines: 4
gap: .07in
raise: 0in
align: bottom
```
hey foundry carries an image initial while this paragraph remains live text.
The wrapped lines should sit close to the illuminated letter before normal
paragraph flow resumes below the ornament.

"""
        return base_frontmatter + "\n" + initial + body

    raise ValueError(f"unknown smoke fixture: {fixture}")


def run_profile_smoke_matrix(
    *,
    profiles: list[str] | tuple[str, ...] | None = None,
    fixture: str = "basic",
    output_dir: str | Path = "generated/profile_smoke_matrix",
    renderer: ProfileSmokeRenderer | None = None,
    create_proofs: bool = False,
    proof_builder=build_visual_proof,
    proof_max_pages: int = 12,
    proof_columns: int = 3,
    proof_dpi: int = 120,
) -> dict[str, Any]:
    """Render a generated fixture across profiles and write a JSON summary.

    Returns the same summary that is written to
    `<output_dir>/profile_smoke_summary.json`.
    """

    selected_profiles = list(profiles or DEFAULT_DOCUMENT_SMOKE_PROFILES)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    source_path = out_root / f"profile_smoke_{fixture}.md"
    source_path.write_text(build_smoke_source(fixture), encoding="utf-8")

    active_renderer = renderer or DocumentRenderer()
    results: list[dict[str, Any]] = []

    for profile in selected_profiles:
        profile_out = out_root / profile
        profile_out.mkdir(parents=True, exist_ok=True)
        try:
            evidence = active_renderer.render(source_path, profile, output_dir=str(profile_out))
        except Exception as exc:  # pragma: no cover - defensive CLI path
            evidence = {
                "status": "error",
                "warnings": [f"render exception: {type(exc).__name__}: {exc}"],
                "output": {"pdf_path": "unknown", "pdf_pages": 0},
                "boundary": {},
            }

        status = "passed" if evidence.get("status") != "error" else "failed"
        boundary = evidence.get("boundary", {}) if isinstance(evidence.get("boundary"), dict) else {}
        output = evidence.get("output", {}) if isinstance(evidence.get("output"), dict) else {}
        evidence_status = evidence.get("status") or ("ok" if status == "passed" else "error")
        result = {
            "profile": profile,
            "status": status,
            "pdf_path": output.get("pdf_path", "unknown"),
            "pdf_pages": output.get("pdf_pages", 0),
            "warnings": evidence.get("warnings", []),
            "target_legacy_profile_tree_mutated": boundary.get("target_legacy_profile_tree_mutated"),
            "render_id": evidence.get("render_id"),
            "evidence_status": evidence_status,
        }
        if create_proofs and status == "passed":
            try:
                result["visual_proof"] = proof_builder(
                    Path(result["pdf_path"]),
                    output_dir=profile_out / "proof",
                    max_pages=proof_max_pages,
                    columns=proof_columns,
                    dpi=proof_dpi,
                )
            except Exception as exc:  # pragma: no cover - defensive CLI path
                result["status"] = "failed"
                result["visual_proof"] = {
                    "status": "error",
                    "error": f"proof exception: {type(exc).__name__}: {exc}",
                }
                result["warnings"] = list(result.get("warnings", [])) + [result["visual_proof"]["error"]]
        results.append(result)

    passed = sum(1 for result in results if result["status"] == "passed")
    failed = len(results) - passed
    summary = {
        "status": "passed" if failed == 0 else "failed",
        "fixture": fixture,
        "source": str(source_path),
        "profiles_requested": len(results),
        "profiles_passed": passed,
        "profiles_failed": failed,
        "proofs_enabled": create_proofs,
        "results": results,
    }
    summary_path = out_root / "profile_smoke_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
