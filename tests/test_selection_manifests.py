"""A2 — selection manifests (keeper rulings 2026-09-01: selector first; the manifest is authoritative)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.manifest_compiler import (
    CompositeBundleCompiler,
    _strip_body_metadata_blocks,
    title_heading,
)
from engine.selection import SelectionError, emit, normalize_value, plain_title, select


def _note(root: Path, name: str, fm: dict | None, body: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\n" if fm is not None else ""
    path.write_text(head + body, encoding="utf-8")
    return path


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "beam"
    _note(root, "b_2025-11-02.md", {"note_role": "keeper-capture", "created": "2025-11-02T09:00:00-04:00"}, "# Bee\n\nB body.\n")
    _note(root, "a.md", {"note_role": '"keeper_capture"', "created": "2025-10-20", "tags": ["Gov"]}, "Kicker line.\n\n# **Ay** title\n\nA body.\n")
    _note(root, "c_2025-11-30.md", {"note_role": "capture", "title": "See"}, "## Not a title\n\nC body.\n")
    _note(root, "undated.md", {"title": "Undated one"}, "Body.\n")
    _note(root, "INDEX.md", {"kind": "index"}, "# Index\n")
    _note(root, "sub/d_2025-12-01.md", {"note_role": "keeper_capture"}, "# Dee\n")
    return root


def _spec(root: Path, **over) -> dict:
    spec = {
        "kind": "selection",
        "schema_version": "selection_manifest_v1",
        "selection_id": "kc",
        "select": {"roots": [str(root)], "exclude": ["INDEX.md"]},
        "order": {"by": "created"},
        "group": {"by": "month", "divider": {"subtitle": "{count} capture{plural}"}},
        "bundle": {"profile": "keeper", "presentation": {"title": "KC"}},
    }
    for key, value in over.items():
        spec[key] = value
    return spec


def test_order_dates_titles_and_month_dividers(corpus, tmp_path):
    result = select(_spec(corpus), spec_path=tmp_path / "s.yaml")
    m = result.manifest
    assert [Path(s["path"]).name for s in m["sources"]] == [
        "a.md", "b_2025-11-02.md", "c_2025-11-30.md", "undated.md"
    ]
    assert [s["selection"]["date_origin"] for s in m["sources"]] == ["created", "created", "filename", "undated"]
    assert [s["title"] for s in m["sources"]] == ["Ay title", "Bee", "See", "Undated one"]
    assert [d["title"] for d in m["section_dividers"]] == ["October 2025", "November 2025", "Undated"]
    assert [d["subtitle"] for d in m["section_dividers"]] == ["1 capture", "2 captures", "1 capture"]
    assert m["sources"][0]["strip_leading_heading"] is True and "strip_leading_heading" not in m["sources"][2]
    assert m["kind"] == "composite_bundle" and m["profile"] == "keeper"
    assert m["resource_roots"] == [str(corpus)]
    assert m["presentation"]["date"]  # dated by composition when not given
    assert m["selection"]["date_origins"] == {"created": 2, "filename": 1, "undated": 1}


def test_where_normalizes_note_role_and_recursion_is_explicit(corpus, tmp_path):
    spec = _spec(corpus, select={"roots": [str(corpus)], "exclude": ["INDEX.md"],
                                 "where": {"note_role": ["keeper_capture"]}})
    names = [Path(s["path"]).name for s in select(spec, spec_path=tmp_path / "s.yaml").manifest["sources"]]
    assert names == ["a.md", "b_2025-11-02.md"]  # quoted and hyphenated spellings both match
    spec["select"]["recursive"] = ["sub"]
    names = [Path(s["path"]).name for s in select(spec, spec_path=tmp_path / "s.yaml").manifest["sources"]]
    assert names == ["a.md", "b_2025-11-02.md", "d_2025-12-01.md"]


def test_created_window_and_tags(corpus, tmp_path):
    spec = _spec(corpus, select={"roots": [str(corpus)], "where": {"created": {"from": "2025-11-01"}}})
    result = select(spec, spec_path=tmp_path / "s.yaml")
    assert {Path(s["path"]).name for s in result.manifest["sources"]} == {"b_2025-11-02.md", "c_2025-11-30.md"}
    assert ("undated" in dict((p.name, r) for p, r in result.excluded)["undated.md"])
    spec["select"]["where"] = {"tags_any": ["gov"]}
    assert [Path(s["path"]).name for s in select(spec, spec_path=tmp_path / "s.yaml").manifest["sources"]] == ["a.md"]


def test_pin_and_unknown_predicate(corpus, tmp_path):
    spec = _spec(corpus, order={"by": "created", "pin": [{"path": str(corpus / "undated.md"), "position": 1}]})
    assert Path(select(spec, spec_path=tmp_path / "s.yaml").manifest["sources"][0]["path"]).name == "undated.md"
    spec["select"]["where"] = {"colour": "blue"}
    with pytest.raises(SelectionError, match="unsupported"):
        select(spec, spec_path=tmp_path / "s.yaml")


def test_emit_writes_an_authoritative_manifest_the_compiler_accepts(corpus, tmp_path):
    spec_path = tmp_path / "kc.selection.yaml"
    spec_path.write_text(yaml.safe_dump({**_spec(corpus), "emit": "kc.composite-bundle.yaml"}), encoding="utf-8")
    out, _ = emit(spec_path)
    manifest = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert out.read_text(encoding="utf-8").startswith("# Composed by `python3 -m cli select")
    compiler = CompositeBundleCompiler()
    assert compiler.validate(manifest) == []
    plan = compiler.compile(manifest, manifest_path=out)
    text = Path(plan.render_source).read_text(encoding="utf-8")
    # the opener carries the title; the body's own H1 is gone, the kicker stays
    assert text.count("Ay") == text.count("Ay title") and "# **Ay** title" not in text
    assert "Kicker line." in text


def test_title_heading_rules():
    assert title_heading("kicker\n\n# T\nx")[2] == "T"
    assert title_heading("## sub\n# T\n") is None
    assert title_heading("```\n# comment\n```\n# Real\n")[2] == "Real"
    assert plain_title("**A** _b_ `c` [d](e)") == "A b c d"
    assert normalize_value(' "Keeper-Capture" ') == "keeper_capture"


def test_body_metadata_blocks_are_removed_but_code_and_rules_stay():
    body = "\n---\ntitle: Old\ndate: 2025-12-06\n---\n\ntext\n\n---\n\nafter rule\n\n```\n---\na: 1\n---\n```\n"
    out, n = _strip_body_metadata_blocks(body)
    assert n == 1
    assert "date: 2025-12-06" not in out and "after rule" in out and "a: 1" in out
