"""D4 — the chapter-opener contract, declared by a profile (promotion map D4)."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

from engine.openers import FILTER, OpenerError, plan_openers


def test_codex0_package_uses_general_opener_geometry_and_filter(tmp_path):
    from engine.profile_resolver import resolve_profile
    resolved = resolve_profile("codex0")
    plan = plan_openers(resolved.openers)
    assert plan is not None
    assert resolved.openers["spill"]["B"] == "0.323em"
    composition = resolved.package_dir / "filters" / "codex0_composition.lua"
    md = _op("One") + "Before the room opens, a long enough first paragraph to need its ordinary space.\n\nSecond paragraph.\n"
    tex = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(composition),
         "--lua-filter", str(FILTER)], input=md, capture_output=True, text=True, check=True).stdout
    assert "\\OFOpenerCapital{B}{efore}" in tex
    assert "CodexLettrine" not in tex
    assert "CodexRaisedCapBox" not in resolved.template_path.read_text()


def test_codex0_opener_breath_keeps_pre_capital_stringify_metric():
    from engine.profile_resolver import resolve_profile
    composition = resolve_profile("codex0").package_dir / "filters" / "codex0_composition.lua"
    # Full paragraph > 62 bytes; without its first word <= 62. The former
    # private capital pass removed that word from stringify before this policy.
    para = "The road does not erase the weather that was always gathering."
    md = _op("One") + "```{=latex}\n\\OFSetRunningTagline{One}\n```\n\n" + para + "\n\nFollowing paragraph.\n"
    tex = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(composition),
         "--lua-filter", str(FILTER)], input=md, capture_output=True, text=True, check=True).stdout
    assert "\\OFOpenerCapital{T}{he}" in tex
    assert "\\CodexBreakOrnament" in tex
    assert "\\noindent \\OFOpenerCapital" not in tex


def test_no_declaration_no_plan():
    assert plan_openers(None) is None and plan_openers({}) is None


def test_declaration_lowers_to_hooks():
    plan = plan_openers({"scale": 2.4, "font_command": "headerfont", "color": "LetterBody",
                         "nudge": "-0.05em", "spill": {"b": "0.323em"}, "epigraph_gap": "2.2em"})
    text = "\n".join(plan.preamble)
    assert "of_openers.tex" in text
    assert "\\renewcommand{\\OFOpenerCapitalScale}{2.4}" in text
    assert "\\renewcommand{\\OFOpenerCapitalFont}{\\headerfont}" in text
    assert "\\textcolor{LetterBody}" in text
    assert "\\OFOpenerSpill{B}{0.323em}" in text
    assert "\\CodexEpigraphToBodyGap}{\\vspace{2.2em}}" in text


@pytest.mark.parametrize("bad", [
    {"capital": "dropped"}, {"scale": 9}, {"font_command": "\\evil"}, {"color": "a b"},
    {"nudge": "1"}, {"spill": {"BB": "1em"}}, {"spill": {"B": "\\x"}}, {"unknown": 1},
])
def test_bad_declarations_are_refused(bad):
    with pytest.raises(OpenerError):
        plan_openers(bad)


OPENER = "\\phantomsection\n\\addcontentsline{toc}{subsection}{%s}\n\\markboth{%s}{%s}\n\n"


def _filtered(md: str, capital: str = "raised") -> str:
    out = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "latex", "--lua-filter", str(FILTER),
         "--metadata", f"of_openers={json.dumps({'capital': capital})}"],
        input=md, capture_output=True, text=True, check=True)
    return out.stdout


def _op(title: str) -> str:
    return OPENER % (title, title, title)


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="needs pandoc")
def test_filter_letters_the_first_prose_paragraph_by_the_contract():
    md = (_op("One") + "The first room.\n\nSecond paragraph.\n\n"
          + _op("Two") + "> An epigraph.\n\nBeneath it.\n\n"
          + _op("Three") + "| a verse\n| line\n\nAfter verse.\n\n"
          + _op("Four") + "\"Quoted opening.\"\n\n"
          + _op("Five") + "*Emphatic* start.\n")
    tex = _filtered(md)
    assert "\\OFOpenerCapital{T}{he} first room." in tex
    assert "Second paragraph." in tex and "\\OFOpenerCapital{S}" not in tex
    assert "\\OFOpenerCapital{B}{eneath} it." in tex           # epigraph skipped
    assert "\\OFOpenerCapital{A}{fter}" not in tex             # verse: no capital
    assert "\\OFOpenerCapital{Q}" not in tex                   # fail-open on a quote mark
    assert "\\OFOpenerCapital{E}{mphatic}" in tex
    assert "\\OFOpenerCapital" not in _filtered(md, capital="none")


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="needs xelatex")
def test_a_package_profile_declaring_openers_renders_a_raised_capital(tmp_path, monkeypatch):
    repo = tmp_path / "profiles"
    pkg = repo / "openers-probe"
    pkg.mkdir(parents=True)
    (pkg / "profile.yaml").write_text(yaml.safe_dump({
        "schema_version": "profile_package_v1", "id": "openers-probe", "extends": "keeper",
        "openers": {"scale": 2.4, "spill": {"B": "0.3em"}, "epigraph_gap": "2.2em"},
    }), encoding="utf-8")
    monkeypatch.setenv("OF_PROFILE_PATH", str(repo))
    src = tmp_path / "a.md"
    src.write_text("---\nuid: a\n---\n\nBefore anything else, a sentence.\n\nMore.\n", encoding="utf-8")
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "openers-probe",
        "profile": "openers-probe", "presentation": {"title": "Openers"},
        "render": {"include_toc": False, "numbersections": False, "suppress_source_wrapper_headings": True},
        "sources": [{"uid": "a", "path": str(src), "role": "primary_anchor", "order": 1,
                     "chapter_opener": {"title": "Chapter One"},
                     "include_frontmatter": "none", "suppress_frontmatter": True}],
    }
    from engine.manifest_compiler import CompositeBundleCompiler
    from renderers.pandoc_renderer import PandocRenderer

    compiler = CompositeBundleCompiler()
    assert compiler.validate(manifest) == []
    ev = PandocRenderer().render(compiler.compile(manifest), output_dir=str(tmp_path / "out"))
    assert ev["status"] == "ok", ev.get("error")
    assert ev["render_metadata"]["openers"]["capital"] == "raised"
    import fitz

    with fitz.open(ev["output"]["pdf_path"]) as doc:
        spans = [s for p in doc for b in p.get_text("dict")["blocks"] for l in b.get("lines", [])
                 for s in l["spans"]]
    caps = [s for s in spans if s["text"].strip() == "B"]
    body = [s["size"] for s in spans if "sentence" in s["text"]]
    assert caps and body and caps[0]["size"] > 2 * body[0]
