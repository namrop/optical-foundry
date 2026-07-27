"""Missing-glyph lint and render-failure regressions."""
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.glyph_lint import format_missing_character_failures, scan_missing_character_warnings
from renderers.document_renderer import DocumentRenderer


def test_scan_missing_character_warnings_reports_codepoint_and_pdf_page():
    log_text = "\n".join(
        [
            '[WARNING] Missing character: There is no 😁 (U+1F601) (U+1F601) in font "Iowan"',
            '[WARNING] Missing character: There is no 😁 (U+1F601) (U+1F601) in font "Iowan"',
            '[WARNING] Missing character: There is no 😁 (U+1F601) (U+1F601) in font "Iowan"',
        ]
    )
    text_extract = "front matter\fmessage ended with �\fback matter"

    failures = scan_missing_character_warnings(log_text, text_extract)

    assert failures == [
        {
            "character": "😁",
            "codepoint": "U+1F601",
            "pdf_pages": [2],
            "warning_count": 3,
        }
    ]
    assert format_missing_character_failures(failures) == "U+1F601 😁 on PDF page 2 (3 compile warnings)"


def test_unknown_glyph_makes_real_codex0_render_fail_loudly(tmp_path):
    """A deliberately injected unassigned codepoint must make the render non-zero-ready."""
    if not shutil.which("pandoc") or not shutil.which("lualatex") or not shutil.which("pdftotext"):
        pytest.skip("pandoc/lualatex/pdftotext not available")

    source = tmp_path / "unknown-glyph.md"
    source.write_text(
        "---\n"
        "uid: unknown-glyph-probe\n"
        "title: Unknown Glyph Probe\n"
        "toc: false\n"
        "numbersections: false\n"
        "---\n\n"
        "# Unknown Glyph Probe\n\n"
        "Deliberately unsupported codepoint: \u0378\n",
        encoding="utf-8",
    )

    evidence = DocumentRenderer().render(source, profile_id="codex0", output_dir=str(tmp_path / "out"))

    assert evidence["status"] == "error"
    assert "U+0378" in evidence["error"]
    assert "PDF page 1" in evidence["error"]
