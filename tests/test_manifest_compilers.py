"""Tests for manifest compilers — composite bundle and label run."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.manifest_compiler import CompositeBundleCompiler, LabelRunCompiler, StickerSheetCompiler, ForgePacketReviewCompiler
from engine.projection_plan import ProjectionPlan

GF = Path(__file__).resolve().parents[1]
SRC = GF / "fixtures" / "sources"


def test_composite_bundle_validate_valid():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [
            {"uid": "src1", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "src2", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_composite_bundle_validate_missing_uid():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [{"role": "primary_anchor", "order": 1}],
    }
    errors = compiler.validate(manifest)
    assert any("missing uid" in e for e in errors)


def test_composite_bundle_validate_duplicate_uid():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [
            {"uid": "dup", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "dup", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
        ],
    }
    errors = compiler.validate(manifest)
    assert any("duplicate uid" in e for e in errors)


def test_composite_bundle_validate_missing_path():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [{"uid": "src1", "path": "/nonexistent/path.md", "role": "primary_anchor", "order": 1}],
    }
    errors = compiler.validate(manifest)
    assert any("not found" in e for e in errors), errors


def test_composite_bundle_compile_produces_plan():
    compiler = CompositeBundleCompiler()
    manifest = {
        "kind": "composite_bundle", "schema_version": "bundle_manifest_v1",
        "bundle_id": "test-bundle", "profile": "cam",
        "sources": [
            {"uid": "fixture-src-001", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1},
            {"uid": "fixture-src-002", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2},
            {"uid": "fixture-src-003", "path": str(SRC / "source-003.md"), "role": "appendix", "order": 3},
        ],
    }
    plan = compiler.compile(manifest)
    assert isinstance(plan, ProjectionPlan)
    assert plan.profile_id == "cam"
    assert plan.has_assembly
    assert plan.assembly is not None
    assert len(plan.assembly.source_order) == 3
    assert plan.source_inventory[0]["uid"] == "fixture-src-001"
    assert plan.render_source.exists()


def test_composite_bundle_compile_bad_manifest_raises():
    compiler = CompositeBundleCompiler()
    try:
        compiler.compile({"kind": "composite_bundle", "schema_version": "bundle_manifest_v1"})
        assert False, "should have raised"
    except ValueError:
        pass


def test_label_run_validate_valid():
    compiler = LabelRunCompiler()
    manifest = {
        "kind": "label_run", "schema_version": "label_run_v1",
        "run_id": "test-run", "sheet_spec": "avery-5164",
        "labels": [
            {"slot": 1, "source": str(SRC / "label-001.md")},
            {"slot": 2, "source": str(SRC / "label-002.md")},
        ],
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_label_run_validate_duplicate_slot():
    compiler = LabelRunCompiler()
    manifest = {
        "kind": "label_run", "schema_version": "label_run_v1",
        "run_id": "test-run", "sheet_spec": "avery-5164",
        "labels": [
            {"slot": 1, "source": str(SRC / "label-001.md")},
            {"slot": 1, "source": str(SRC / "label-002.md")},
        ],
    }
    errors = compiler.validate(manifest)
    assert any("duplicate slot" in e for e in errors)


def test_label_run_compile_produces_plan():
    compiler = LabelRunCompiler()
    manifest = {
        "kind": "label_run", "schema_version": "label_run_v1",
        "run_id": "test-run", "sheet_spec": "avery-5164",
        "profile": "labels-avery-5164",
        "labels": [
            {"slot": 1, "source": str(SRC / "label-001.md")},
            {"slot": 2, "source": str(SRC / "label-002.md")},
        ],
    }
    plan = compiler.compile(manifest)
    assert isinstance(plan, ProjectionPlan)
    assert plan.has_assembly
    assert len(plan.assembly.source_order) == 2
    assert plan.render_source.exists()


def test_sticker_sheet_validate():
    compiler = StickerSheetCompiler()
    manifest = {
        "kind": "sticker_sheet", "schema_version": "sticker_sheet_v1",
        "sheet_id": "test-stickers", "profile": "sticker-sheet",
        "layout": {"grid": [2, 2], "cell_size": [2.5, 2.5]},
        "cells": [
            {"position": [0, 0], "content": "Sticker A"},
            {"position": [0, 1], "content": "Sticker B"},
            {"position": [1, 0], "content": "Sticker C"},
            {"position": [1, 1], "content": "Sticker D"},
        ],
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors


def test_packet_review_validate():
    compiler = ForgePacketReviewCompiler()
    manifest = {
        "kind": "forge_packet_review", "schema_version": "packet_review_manifest_v1",
        "profile": "prometheus-packet",
        "packet": {
            "path": str(GF),
            "include": ["BEAM.md", "DESIGN.md"],
        },
    }
    errors = compiler.validate(manifest)
    assert errors == [], errors
