from pathlib import Path
import shutil

import pytest

from engine.manifest_compiler import CompositeBundleCompiler
from renderers.pandoc_renderer import PandocRenderer


@pytest.mark.skipif(
    not shutil.which("pandoc")
    or not shutil.which("lualatex")
    or not shutil.which("pdftotext"),
    reason="Pandoc/LuaLaTeX/pdftotext toolchain not installed",
)
def test_body_folio_start_preserves_roman_frontmatter_and_seats_first_body_folio(
    tmp_path: Path,
):
    front = tmp_path / "front.md"
    body = tmp_path / "body.md"
    front.write_text("# Front sentinel\n\nFront matter.\n")
    body.write_text("# Body sentinel\n\nBody matter.\n")

    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": "body-folio-start-probe",
        "profile": "codex0",
        "presentation": {
            "title": "",
            "subtitle": "",
            "authors": [],
            "date": "2026-07-27",
        },
        "variables": {"body_folio_start": 201},
        "sources": [
            {
                "uid": "front",
                "path": str(front),
                "role": "frontmatter",
                "order": 1,
                "include_frontmatter": "none",
                "suppress_frontmatter": True,
            },
            {
                "uid": "body",
                "path": str(body),
                "role": "primary_anchor",
                "order": 2,
                "include_frontmatter": "none",
                "suppress_frontmatter": True,
            },
        ],
        "render": {
            "include_toc": False,
            "page_size": "half_letter",
            "preserve_source_provenance": False,
            "emit_visible_provenance": False,
            "text_integrity_check": True,
        },
        "validation": {
            "require_all_source_paths": True,
            "require_unique_uids": True,
        },
    }

    plan = CompositeBundleCompiler().compile(manifest)
    output_dir = tmp_path / "out"
    evidence = PandocRenderer().render(plan, str(output_dir))

    assert evidence["status"] == "ok", evidence.get("error")
    pages = (output_dir / "body-folio-start-probe.txt").read_text().split("\f")
    front_page = next(page for page in pages if "Front sentinel" in page)
    body_page = next(page for page in pages if "Body sentinel" in page)
    assert front_page.rstrip().endswith("i")
    assert body_page.rstrip().endswith("201")
