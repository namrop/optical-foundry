"""A5 — the extent of a work (promotion map A5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.extent import ExtentError, apply_extent, prose_words, round_words, words_to_english
from engine.volumes import split_manifest


def test_prose_words_counts_what_a_reader_receives():
    text = """---
title: Not counted
---

# A heading of four

Plain prose here, with a [link text](http://x.example/y) and a footnote.[^1]

<!-- cx0:variant archival --> hidden <!-- /cx0:variant -->

```of-image
path: assets/plate.png
```

```{=latex}
\\clearpage
```

\\OFChapterOpener{Three visible words}
\\vspace{1em}

::: breath
:::

[^1]: The note counts.
"""
    # 4 heading + 10 prose + 1 variant body ("hidden": the markers go, the text
    # between them is read) + 3 opener + 3 footnote text; nothing from
    # frontmatter, comment markers, fences, or LaTeX machinery.
    assert prose_words(text) == 4 + 10 + 1 + 3 + 3


def test_visible_commands_are_profile_extensible():
    line = "\\CodexOpenerEpigraph{two words}\n"
    assert prose_words(line) == 0
    assert prose_words(line, visible_commands=["CodexOpenerEpigraph"]) == 2


@pytest.mark.parametrize("n,words", [
    (0, "zero"), (7, "seven"), (21, "twenty-one"), (100, "one hundred"),
    (94000, "ninety-four thousand"), (120000, "one hundred twenty thousand"),
    (1500, "one thousand five hundred"), (2_000_000, "2,000,000"),
])
def test_words_to_english(n, words):
    assert words_to_english(n) == words


def test_round_words():
    assert round_words(94_499) == 94_000 and round_words(94_501) == 95_000
    with pytest.raises(ExtentError):
        round_words(10, 0)


def _src(tmp: Path, name: str, words: int) -> dict:
    p = tmp / name
    p.write_text("---\nuid: x\n---\n" + " ".join(["word"] * words) + "\n", encoding="utf-8")
    return {"uid": name, "path": str(p), "role": "primary_anchor", "order": len(name)}


def test_apply_extent_sets_colophon_words_unless_the_manifest_does(tmp_path):
    m = {"presentation": {"extent": {"round": 100}}, "sources": [_src(tmp_path, "a.md", 1250), _src(tmp_path, "bb.md", 1300)]}
    rec = apply_extent(m)
    assert rec == {"exact": 2550, "rounded": 2600, "printed": "two thousand six hundred", "sources": 2}
    assert m["variables"]["colophon_words"] == "two thousand six hundred"
    kept = {"presentation": {"extent": {}}, "variables": {"colophon_words": 5}, "sources": m["sources"]}
    assert apply_extent(kept) is None and kept["variables"]["colophon_words"] == 5
    assert apply_extent({"sources": m["sources"]}) is None
    num = {"presentation": {"extent": {"form": "number"}}, "sources": m["sources"]}
    apply_extent(num)
    assert num["variables"]["colophon_words"] == 3000


def test_volumes_carry_the_whole_works_extent(tmp_path):
    sources = [_src(tmp_path, "a.md", 600), _src(tmp_path, "bb.md", 900)]
    m = {"kind": "composite_bundle", "bundle_id": "w", "presentation": {"extent": {"round": 100, "form": "number"}},
         "sources": sources, "volumes": [{"id": "i"}, {"id": "ii", "before_source_uid": "bb.md"}]}
    parts = split_manifest(m)
    assert [p["variables"]["colophon_words"] for p in parts] == [1500, 1500]
    assert parts[1]["volume"]["extent"]["exact"] == 1500
    assert "variables" not in m  # the caller's manifest is not mutated


def test_bundle_compiler_prints_the_measure_into_the_colophon(tmp_path):
    from engine.manifest_compiler import CompositeBundleCompiler

    body = tmp_path / "body.md"
    body.write_text("---\nuid: b\n---\n\n" + " ".join(["word"] * 940) + "\n", encoding="utf-8")
    colophon = tmp_path / "colophon.md"
    colophon.write_text("---\nuid: c\n---\n\nDrawn down to <<COLOPHON_WORDS>> words.\n", encoding="utf-8")
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "extent-test", "profile": "keeper",
        "presentation": {"title": "X", "extent": {"round": 100}},
        "sources": [
            {"uid": "b", "path": str(body), "role": "primary_anchor", "order": 1},
            {"uid": "c", "path": str(colophon), "role": "appendix", "order": 2},
        ],
    }
    compiler = CompositeBundleCompiler()
    assert compiler.validate(manifest) == []
    plan = compiler.compile(manifest)
    # 940 + "Drawn down to words." (4) -> 944 -> 900
    assert "Drawn down to nine hundred words." in plan.render_source.read_text()
    assert plan.boundary_assertions["extent"] == {"exact": 944, "rounded": 900, "printed": "nine hundred", "sources": 2}
    assert "variables" not in manifest
