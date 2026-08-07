"""End-to-end proof of the ornament page-position law (Luis-ruled 2026-08-07).

The law is render-time only: sources keep saying what the author meant, and the
engine decides which ornaments survive pagination.

  1. No ornament at the TOP of a page, ever.
  2. No ornament at the BOTTOM except a tailpiece or a threshold -- either/or,
     never both.

These tests drive real LuaLaTeX with the template's own law block (extracted
from ``codex0.tex``, so the tests cannot drift from the shipped code) and
measure the resulting PDF geometrically. A page-position law can only be proved
on a paginated page; string assertions about the macro live in
``test_template_contracts.py``.
"""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

GF = Path(__file__).resolve().parents[1]
CODEX0_TEMPLATE = GF / "profiles" / "40_latex_import" / "templates" / "codex0.tex"

LAW_START = "% --- Ornament page-position law"
LAW_END = "% --- end ornament page-position law"

pytestmark = pytest.mark.skipif(
    not shutil.which("lualatex"),
    reason="LuaLaTeX not installed",
)


def _law_block() -> str:
    text = CODEX0_TEMPLATE.read_text(encoding="utf-8")
    start = text.index(LAW_START)
    end = text.index(LAW_END)
    return text[start : text.index("\n", end) + 1]


def _compile(tmp_path: Path, body: str, enabled: bool = True) -> Path:
    """Compile a narrow-page probe document and return the PDF path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "law.tex").write_text(_law_block(), encoding="utf-8")
    switch = "" if enabled else "\\CodexOrnamentLawDisable"
    src = tmp_path / "probe.tex"
    src.write_text(
        "\\documentclass[11pt]{article}\n"
        "\\usepackage[paperwidth=4in,paperheight=3.2in,margin=0.4in]{geometry}\n"
        "\\parindent=1em\n"
        "\\input{law.tex}\n"
        "\\newcommand{\\Orn}[1]{\\CodexOrnamentBand{#1}{"
        "\\par\\vspace{0.5em}{\\centering\\rule{1in}{6pt}\\par}\\vspace{0.5em}}}\n"
        f"{switch}\n"
        "\\begin{document}\n"
        f"{body}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["lualatex", "-interaction=nonstopmode", "-halt-on-error", "probe.tex"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
    )
    pdf = tmp_path / "probe.pdf"
    assert pdf.exists(), result.stdout[-3000:]
    return pdf


def _bands(pdf: Path):
    """Per page: (ornament rules above all text, ornament rules below all text).

    The probe's ornaments are 1in x 6pt rules; the folio is the only text
    outside the text block, so it is excluded by position.
    """
    fitz = pytest.importorskip("fitz")
    doc = fitz.open(pdf)
    top_total = 0
    bottom_total = 0
    per_page = []
    for page in doc:
        body_bottom = page.rect.height - 0.4 * 72  # bottom text margin
        lines = [
            line["bbox"]
            for block in page.get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block.get("lines", [])
            if (line["bbox"][1] + line["bbox"][3]) / 2 < body_bottom
        ]
        rules = [
            d["rect"]
            for d in page.get_drawings()
            if 60 < d["rect"].width < 90 and d["rect"].height < 10
        ]
        if not lines:
            per_page.append((0, 0))
            continue
        first = min(b[1] for b in lines)
        last = max(b[3] for b in lines)
        top = sum(1 for r in rules if (r.y0 + r.y1) / 2 < first)
        bottom = sum(1 for r in rules if (r.y0 + r.y1) / 2 > last)
        top_total += top
        bottom_total += bottom
        per_page.append((top, bottom))
    return top_total, bottom_total, per_page


PROSE = "\n".join(
    f"\\noindent P{i}. " + "filler words to run the measure " * ((i % 3) + 1) + "\\par"
    + ("\n\\Orn{1}" if i % 3 == 0 else "")
    for i in range(1, 61)
)


def test_tier_ornaments_never_survive_at_a_page_top_or_bottom(tmp_path):
    """The headline law, measured on a real multi-page document."""
    control = _compile(tmp_path / "control", PROSE, enabled=False)
    treated = _compile(tmp_path / "treated", PROSE, enabled=True)

    ctop, cbottom, _ = _bands(control)
    ttop, tbottom, _ = _bands(treated)

    assert ctop > 0, "probe did not strand any ornament at a page top"
    assert ttop == 0
    assert tbottom == 0
    assert (ttop + tbottom) < (ctop + cbottom)


def test_suppression_takes_the_ornaments_vertical_space_with_it(tmp_path):
    """A dropped top ornament leaves no hole: the first baseline is unmoved.

    Recomputing the page's topskip for the box that becomes first is the whole
    of this test — without it, corrected pages ride high and read as a
    different text block from their neighbours.
    """
    fitz = pytest.importorskip("fitz")
    treated = _compile(tmp_path, PROSE, enabled=True)
    doc = fitz.open(treated)

    firsts = set()
    for page in doc:
        lines = [
            line["bbox"]
            for block in page.get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block.get("lines", [])
        ]
        if lines:
            firsts.add(round(min(b[1] for b in lines), 1))

    assert len(firsts) == 1, f"first-baseline drift across pages: {sorted(firsts)}"


def test_a_tailpiece_may_sit_at_a_page_foot(tmp_path):
    """Rule 2's exception. A tailpiece closes a chapter; a page foot is its home."""
    body = "\n".join(f"\\noindent L{i} short line.\\par" for i in range(1, 9))
    body += "\n\\Orn{2}\n\\newpage\n\\noindent next page.\\par"
    pdf = _compile(tmp_path, body)

    _, bottom, per_page = _bands(pdf)
    assert bottom == 1, per_page


def test_a_tailpiece_and_a_threshold_at_one_foot_is_either_or(tmp_path):
    """Both at one page foot: keep the first, drop the second, warn."""
    body = "\n".join(f"\\noindent L{i} short line.\\par" for i in range(1, 9))
    body += "\n\\Orn{2}\\Orn{3}\n\\newpage\n\\noindent next page.\\par"
    pdf = _compile(tmp_path, body)

    _, bottom, per_page = _bands(pdf)
    assert bottom == 1, per_page

    log = (tmp_path / "probe.log").read_text(encoding="utf-8", errors="replace")
    flat = re.sub(r"\n", "", log)
    assert "either/or" in flat
    assert "dropped threshold ornament" in flat


def test_a_page_that_is_only_ornament_is_left_alone(tmp_path):
    """Fail-safe: never empty a page.

    A page whose whole body is an ornament is a deliberate ornamental page, not
    a pagination accident, and the law must not eat it.
    """
    body = "\\noindent first.\\par\n\\newpage\n\\Orn{1}\n\\newpage\n\\noindent last.\\par"
    pdf = _compile(tmp_path, body)

    fitz = pytest.importorskip("fitz")
    doc = fitz.open(pdf)
    rules = sum(
        1
        for page in doc
        for d in page.get_drawings()
        if 60 < d["rect"].width < 90 and d["rect"].height < 10
    )
    assert rules == 1

    log = (tmp_path / "probe.log").read_text(encoding="utf-8", errors="replace")
    assert "left alone" in re.sub(r"\n", "", log)


def test_suppression_does_not_provoke_underfull_page_warnings(tmp_path):
    """The reclaimed height is parked in a \\fil at the page foot.

    Without it every corrected page reports an underfull \\vbox while \\output
    is active, which would bury real warnings in a book-length render.
    """
    _compile(tmp_path, PROSE, enabled=True)
    log = (tmp_path / "probe.log").read_text(encoding="utf-8", errors="replace")

    assert "Underfull \\vbox" not in log
