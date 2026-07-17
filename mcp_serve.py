#!/usr/bin/env python3
"""Optical Foundry MCP server.

Exposes the Foundry render lane over MCP (FastMCP), so agents can render
profile-branded PDFs from Markdown without touching LaTeX, Pandoc YAML, or brand
assets. The contract to callers is deliberately narrow: **Markdown + a profile
name**. Templates, Pandoc defaults, and brand assets stay server-owned inside
the profile, which is the whole point of the Foundry (do not add a "pass me raw
LaTeX/YAML" tool — that dissolves the profile abstraction).

Run (stdio):
    python3 -m mcp_serve            # from the Foundry repo root
or:
    python3 mcp_serve.py

Requires: mcp SDK, plus the Foundry's system toolchain on PATH
(pandoc, xelatex, and figure tools). Runs where that toolchain lives (Sol).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make engine/renderers/cli/service importable when run as a script.
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP

import service
from engine.profile_checker import check_all_profiles_json
from engine.visual_proof import build_visual_proof

mcp = FastMCP("optical-foundry")

_TMP_SOURCES = _ROOT / "generated" / "_mcp_inline_sources"


def _distill(evidence: dict) -> dict:
    """Reduce a full evidence sidecar to the fields a caller needs."""
    rm = evidence.get("render_metadata", {}) or {}
    out = evidence.get("output", {}) or {}
    boundary = evidence.get("boundary", {}) or {}
    return {
        "status": evidence.get("status"),
        "success": rm.get("success"),
        "pdf_path": out.get("pdf_path"),
        "pages": out.get("pdf_pages"),
        "pdf_sha256": out.get("pdf_sha256"),
        "warnings": rm.get("warnings") or [],
        "error": rm.get("error") or evidence.get("error"),
        "placeholder_assets": boundary.get("placeholder_assets"),
        "evidence_path": evidence.get("evidence_path"),
    }


@mcp.tool()
def list_profiles() -> str:
    """List available render profiles and their capabilities as JSON.

    Use this to discover valid `profile` values for render_report (e.g.
    'generic-report', or the 'yugen_risk'/'yugen_tech'/'yugen_civic' report
    family).
    """
    return check_all_profiles_json()


@mcp.tool()
def render_report(
    markdown_path: str | None = None,
    markdown_text: str | None = None,
    profile: str = "generic-report",
    output_dir: str | None = None,
) -> dict:
    """Render one Markdown report to a branded PDF through a profile.

    Provide exactly one of `markdown_path` (a file on disk) or `markdown_text`
    (inline Markdown, optionally with a YAML frontmatter block for title /
    subtitle / author / date). `profile` defaults to 'generic-report'; call
    list_profiles to discover others. Returns the PDF path plus render evidence
    (pages, sha256, warnings, placeholder-asset flag).
    """
    if bool(markdown_path) == bool(markdown_text):
        raise ValueError("provide exactly one of markdown_path or markdown_text")

    if markdown_text is not None:
        _TMP_SOURCES.mkdir(parents=True, exist_ok=True)
        # Stable-ish name derived from content length; avoids clock/random deps.
        src = _TMP_SOURCES / f"inline_{abs(hash(markdown_text)) & 0xFFFFFFFF:08x}.md"
        src.write_text(markdown_text)
        source = src
    else:
        source = Path(markdown_path)  # type: ignore[arg-type]
        if not source.exists():
            raise ValueError(f"markdown_path does not exist: {source}")

    evidence = service.render_document(source, profile, output_dir=output_dir)
    return _distill(evidence)


@mcp.tool()
def render_manifest(manifest_path: str, output_dir: str | None = None) -> dict:
    """Render a typed manifest (bundle / cam_stack / codex_bundle / packet review).

    Use for multi-source assembled artifacts rather than a single document.
    Returns the PDF path plus render evidence.
    """
    evidence = service.render_manifest(manifest_path, output_dir=output_dir)
    return _distill(evidence)


@mcp.tool()
def contact_sheet(pdf_path: str, output_dir: str | None = None, max_pages: int = 12) -> dict:
    """Rasterize a rendered PDF into a labeled contact sheet for a quick visual check."""
    out = Path(output_dir) if output_dir else _ROOT / "generated" / "proofs" / "mcp_contact_sheet"
    return build_visual_proof(Path(pdf_path), output_dir=out, max_pages=max_pages)


if __name__ == "__main__":
    mcp.run()
