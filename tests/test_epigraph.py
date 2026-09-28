from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.epigraph import epigraph_from_file, epigraph_from_frontmatter
from engine.manifest_compiler import CompositeBundleCompiler


def test_harvest_maps_every_layered_field():
    fm = {
        "epigraph_line": "The river is everywhere at once.",
        "epigraph_speaker": "Vasudeva",
        "epigraph_context": "at the ferry",
        "epigraph_author": "Hermann Hesse",
        "epigraph_source": "Siddhartha",
        "epigraph_translator": "Hilda Rosner",
        "epigraph_date": "1922",
        "epigraph_register": "literary",
        "title": "ignored",
    }
    assert epigraph_from_frontmatter(fm) == {
        "text": "The river is everywhere at once.",
        "speaker": "Vasudeva",
        "context": "at the ferry",
        "author": "Hermann Hesse",
        "source": "Siddhartha",
        "translator": "Hilda Rosner",
        "date": "1922",
        "register": "literary",
    }


@pytest.mark.parametrize("fm", [None, {}, {"epigraph_line": "  "}, {"epigraph_author": "x"}, "not a mapping"])
def test_no_line_means_no_epigraph(fm):
    assert epigraph_from_frontmatter(fm) is None


def test_blank_optional_fields_are_dropped():
    assert epigraph_from_frontmatter({"epigraph_line": "x", "epigraph_translator": "", "epigraph_date": None}) == {"text": "x"}


def test_harvest_from_file(tmp_path):
    p = tmp_path / "00_divider.md"
    p.write_text("---\ntitle: Divider\nepigraph_line: Keep going.\nepigraph_author: Someone\n---\n\nbody\n")
    assert epigraph_from_file(p) == {"text": "Keep going.", "author": "Someone"}
    assert epigraph_from_file(tmp_path / "absent.md") is None
    (tmp_path / "plain.md").write_text("no frontmatter\n")
    assert epigraph_from_file(tmp_path / "plain.md") is None


def _manifest(tmp_path: Path, opener: dict) -> tuple[dict, Path]:
    src = tmp_path / "passage.md"
    src.write_text("---\ntitle: P\nepigraph_line: From the source itself.\nepigraph_author: Author A\n---\n\nBody text.\n")
    divider = tmp_path / "00_divider.md"
    divider.write_text("---\ntitle: D\nepigraph_line: From the divider.\nepigraph_register: witness\n---\n")
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": "epigraph-test",
        "profile": "keeper",
        "presentation": {"title": "T"},
        "sources": [
            {
                "uid": "s1",
                "path": str(src),
                "role": "primary_anchor",
                "order": 1,
                "suppress_frontmatter": True,
                "chapter_opener": {"title": "Chapter One", **opener},
            }
        ],
    }
    manifest_path = tmp_path / "m.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest))
    return manifest, manifest_path


def _compiled_markdown(manifest: dict, manifest_path: Path) -> str:
    plan = CompositeBundleCompiler().compile(manifest, manifest_path=str(manifest_path))
    return Path(plan.render_source).read_text()


def test_compiler_harvests_epigraph_from_named_file(tmp_path):
    manifest, mpath = _manifest(tmp_path, {"epigraph_from": "00_divider.md"})
    md = _compiled_markdown(manifest, mpath)
    assert "\\CodexOpenerEpigraph{witness}{From the divider.}" in md


def test_compiler_harvests_epigraph_from_source_frontmatter(tmp_path):
    manifest, mpath = _manifest(tmp_path, {"epigraph_from_source": True})
    md = _compiled_markdown(manifest, mpath)
    assert "\\CodexOpenerEpigraph{literary}{From the source itself.}{}{}{Author A}" in md


def test_explicit_epigraph_wins_over_harvest(tmp_path):
    manifest, mpath = _manifest(tmp_path, {"epigraph": {"text": "Explicit."}, "epigraph_from": "00_divider.md"})
    md = _compiled_markdown(manifest, mpath)
    assert "{Explicit.}" in md and "From the divider." not in md


def test_unresolvable_epigraph_from_is_a_manifest_error(tmp_path):
    manifest, mpath = _manifest(tmp_path, {"epigraph_from": "missing.md"})
    with pytest.raises(ValueError, match="epigraph_from does not resolve"):
        _compiled_markdown(manifest, mpath)
