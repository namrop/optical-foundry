"""One preamble per render (architecture review 2026-10-01, candidate 2; ruling 01a0f8ba-4937)."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from engine.preamble import ORIGINS, Preamble, source_header_includes
from renderers.document_renderer import DocumentRenderer
from renderers.pandoc_renderer import PandocRenderer


def test_lines_follow_origin_order_not_call_order_and_dedupe():
    p = Preamble()
    p.add("image_bake", "% bake")
    p.add("strikeout", "% strike")
    p.add("source", ["\\usepackage{a}", "\\usepackage{b}"])
    p.add("page_geometry", "\\usepackage{a}")  # already present from the source
    assert p.lines() == ["\\usepackage{a}", "\\usepackage{b}", "% strike", "% bake"]
    assert p.evidence(None)["lines_by_origin"] == {"source": 2, "page_geometry": 1, "strikeout": 1, "image_bake": 1}


def test_unknown_origin_is_refused():
    with pytest.raises(ValueError, match="unknown preamble origin"):
        Preamble().add("misc", "x")


def test_empty_preamble_writes_no_file(tmp_path):
    assert Preamble().write(tmp_path, "r") is None


def test_source_header_includes_accepts_both_spellings(tmp_path):
    src = tmp_path / "s.md"
    src.write_text("---\nheader_includes: \\usepackage{x}\n---\nbody\n", encoding="utf-8")
    assert source_header_includes(src) == ["\\usepackage{x}"]
    assert "source" == ORIGINS[0]


needs_tex = pytest.mark.skipif(
    not (shutil.which("pandoc") and shutil.which("xelatex") and shutil.which("pdftotext")),
    reason="pandoc/xelatex/pdftotext missing",
)


@needs_tex
def test_source_lines_survive_an_include_file(tmp_path):
    """A draft render gives pandoc an include file, which makes it drop metadata
    header-includes. The source's lines used to survive only when an overlay
    copied them forward; now the one preamble carries them, and no overlay does."""
    src = tmp_path / "s.md"
    src.write_text(
        "---\ntitle: P\ntoc: false\nnumbersections: false\n"
        "header-includes:\n  - \\newcommand{\\OFProbe}{survived}\n---\n\nThe probe \\OFProbe{} here.\n",
        encoding="utf-8",
    )
    plan = DocumentRenderer().build_plan(src, "generic-report")
    evidence = PandocRenderer().render(plan, output_dir=str(tmp_path / "out"))
    assert evidence["status"] == "ok", evidence.get("error")
    origins = evidence["render_metadata"]["preamble"]["lines_by_origin"]
    assert origins["source"] == 1
    import yaml
    for overlay in (tmp_path / "out").glob("*.yaml"):
        assert "header-includes" not in ((yaml.safe_load(overlay.read_text()) or {}).get("variables") or {})
    text = subprocess.run(["pdftotext", evidence["output"]["pdf_path"], "-"], capture_output=True, text=True).stdout
    assert "The probe survived here." in " ".join(text.split())
