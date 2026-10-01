"""The bundle schema is the manifest's whole interface (architecture review
2026-10-01, candidate 4; ruling 01a0f8ba-4937)."""
from __future__ import annotations

import ast
import glob
from pathlib import Path

import pytest
import yaml

from engine.manifest_compiler import BUNDLE_SCHEMA_PATH, CompositeBundleCompiler, bundle_schema_errors

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = yaml.safe_load(BUNDLE_SCHEMA_PATH.read_text(encoding="utf-8"))

# Variable names the bundle compiler uses for each part of a manifest.
NAME_TO_PATH = {
    "manifest": (),
    "pres": ("presentation",),
    "title_page": ("presentation", "title_page"),
    "src": ("sources", "[]"),
    "s": ("sources", "[]"),
    "_opener_cfg_early": ("sources", "[]", "chapter_opener"),
    "opener": ("sources", "[]", "chapter_opener"),
    "divider": ("section_dividers", "[]"),
    "source_cfg": ("section_dividers", "[]", "source"),
    "render_cfg": ("render",),
    "gen_cfg": ("generated",),
    "rg": ("generated", "reader_guide"),
    "aw": ("generated", "afterword"),
    "fig": ("figures", "[]"),
    "f": ("figures", "[]"),
}
# Reads of these names outside the bundle path belong to other manifest kinds.
OTHER_KIND_KEYS = {"document_id", "source", "metadata", "packet", "labels", "layout", "cells",
                   "sheet_id", "sheet_spec", "output_name", "run_id", "render_id"}


def _node(path):
    node = SCHEMA
    for part in path:
        node = node["items"] if part == "[]" else node["properties"][part]
    return node


def _bundle_reads():
    tree = ast.parse((ROOT / "engine" / "manifest_compiler.py").read_text(encoding="utf-8"))
    scopes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CompositeBundleCompiler"]
    # Module-level helpers that take a divider or an opener belong to the bundle path.
    scopes += [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and {a.arg for a in n.args.args} & {"divider", "source_cfg", "opener"}
    ]
    reads = set()
    for scope in scopes:
        for node in ast.walk(scope):
            if (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name) and node.func.value.id in NAME_TO_PATH
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            ):
                reads.add((node.func.value.id, node.args[0].value))
    return reads


def test_every_key_the_bundle_compiler_reads_is_declared():
    missing = []
    for name, key in sorted(_bundle_reads()):
        if name == "manifest" and key in OTHER_KIND_KEYS:
            continue
        props = _node(NAME_TO_PATH[name]).get("properties", {})
        if key not in props:
            missing.append(f"{'.'.join(NAME_TO_PATH[name]) or '(top)'}.{key}")
    assert missing == []


def _unread_keys(node, path=()):
    for key, child in (node.get("properties") or {}).items():
        if child.get("x-of-unread"):
            yield path + (key,)
        yield from _unread_keys(child, path + (key,))
    if "items" in node:
        yield from _unread_keys(node["items"], path + ("[]",))


def test_keys_declared_unread_are_not_read_by_the_bundle_compiler():
    reads = {(NAME_TO_PATH[name], key) for name, key in _bundle_reads()}
    read_anyway = [path for path in _unread_keys(SCHEMA) if (tuple(path[:-1]), path[-1]) in reads]
    assert read_anyway == []
    # and the dead render/validation keys appear nowhere in the engine at all
    engine_text = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "engine").glob("*.py"))
    for key in ("text_integrity_check", "visual_page_samples", "page_sample_format",
                "passthrough_single_source", "emit_provenance_section", "required_text_markers"):
        assert f'"{key}"' not in engine_text, key


def test_strict_objects_reject_unknown_keys():
    for path in [(), ("presentation",), ("sources", "[]"), ("section_dividers", "[]"), ("render",), ("figures", "[]")]:
        assert _node(path).get("additionalProperties") is False, path


def _manifest(tmp_path, **extra):
    src = tmp_path / "s.md"
    src.write_text("# S\n\nText.\n", encoding="utf-8")
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "bundle_id": "schema-probe",
        "profile": "keeper",
        "sources": [{"uid": "s", "path": str(src), "role": "primary_anchor", "order": 1}],
    }
    manifest.update(extra)
    return manifest


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda m: m["sources"][0].update(chapter_openr={"title": "x"}), "chapter_openr"),
        (lambda m: m.update(render={"numbering_strategy": "section_divider"}), "section_divider"),
        (lambda m: m.update(render={"include_tok": False}), "include_tok"),
        (lambda m: m.update(presentaton={"title": "x"}), "presentaton"),
    ],
)
def test_typos_fail_validation_instead_of_being_ignored(tmp_path, mutate, needle):
    manifest = _manifest(tmp_path)
    assert CompositeBundleCompiler().validate(manifest) == []
    mutate(manifest)
    errors = CompositeBundleCompiler().validate(manifest)
    assert any(needle in e for e in errors), errors


def test_unquoted_yaml_dates_are_still_strings(tmp_path):
    manifest = yaml.safe_load(
        "kind: composite_bundle\nschema_version: bundle_manifest_v1\nbundle_id: d\nprofile: keeper\n"
        "presentation: {date: 2026-10-01}\nsources: []\n"
    )
    assert not [e for e in bundle_schema_errors(manifest) if "date" in e]


def test_every_bundle_manifest_in_the_repo_validates():
    files = sorted(glob.glob(str(ROOT / "manifests" / "*.yaml")) + glob.glob(str(ROOT / "fixtures" / "**" / "*.yaml"), recursive=True))
    checked = 0
    for f in files:
        data = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema_version") == "bundle_manifest_v1":
            checked += 1
            assert bundle_schema_errors(data) == [], f
    assert checked >= 5
