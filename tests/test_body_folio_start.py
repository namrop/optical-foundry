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


def _probe_manifest(tmp_path: Path, bundle_id: str, body_folio_start: int) -> dict:
    front = tmp_path / f"{bundle_id}-front.md"
    body = tmp_path / f"{bundle_id}-body.md"
    front.write_text("# Front sentinel\n\nFront matter.\n")
    body.write_text("# Body sentinel\n\nBody matter.\n")
    return {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": bundle_id,
        "profile": "codex0",
        "presentation": {
            "title": "",
            "subtitle": "",
            "authors": [],
            "date": "2026-08-06",
        },
        "variables": {"body_folio_start": body_folio_start},
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


@pytest.mark.skipif(
    not shutil.which("pandoc")
    or not shutil.which("lualatex")
    or not shutil.which("pdftotext"),
    reason="Pandoc/LuaLaTeX/pdftotext toolchain not installed",
)
@pytest.mark.parametrize("body_folio_start", [192, 201])
def test_body_folio_start_keeps_folio_parity_on_physical_parity(
    tmp_path: Path, body_folio_start: int
):
    """The seated body folio must land on a physical page of the SAME parity.

    `twoside` derives inner/outer margins, running heads and the outer-margin
    rails from \\value{page}; imposition folds by physical sheet position (input
    page 1 = outermost recto). If the two parities disagree, every recto is
    typeset as a verso and every rail folds to the gutter instead of the fore
    edge — the build 45/46 Volume II print defect. An EVEN seat costs one
    unnumbered parity leaf; an ODD seat costs nothing.
    """

    bundle_id = f"body-folio-parity-{body_folio_start}"
    plan = CompositeBundleCompiler().compile(_probe_manifest(tmp_path, bundle_id, body_folio_start))
    output_dir = tmp_path / f"out-{body_folio_start}"
    evidence = PandocRenderer().render(plan, str(output_dir))

    assert evidence["status"] == "ok", evidence.get("error")
    pages = (output_dir / f"{bundle_id}.txt").read_text().split("\f")
    physical = next(
        index for index, page in enumerate(pages, start=1) if "Body sentinel" in page
    )
    body_page = pages[physical - 1]
    assert body_page.rstrip().endswith(str(body_folio_start))
    assert physical % 2 == body_folio_start % 2, (
        f"body folio {body_folio_start} seated on physical page {physical}: "
        "folio parity and physical-sheet parity disagree, so twoside layout is "
        "inverted and imposed rails will fold to the gutter"
    )
