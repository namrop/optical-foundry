"""Tests for engine.schemas — subtype detection and classification."""
from pathlib import Path

import yaml

from engine.schemas import detect_subtype, is_single_document, MANIFEST_CLASS_NAMES


ROOT = Path(__file__).resolve().parents[1]


def test_detect_bundle_manifest():
    assert detect_subtype({"kind": "composite_bundle", "schema_version": "bundle_manifest_v1"}) == "bundle"
    assert detect_subtype({"kind": "cam_stack", "schema_version": "bundle_manifest_v1"}) == "bundle"
    assert detect_subtype({"kind": "codex_bundle", "schema_version": "bundle_manifest_v1"}) == "bundle"


def test_detect_label_and_sticker():
    assert detect_subtype({"kind": "label_run", "schema_version": "label_run_v1"}) == "label"
    assert detect_subtype({"kind": "sticker_sheet", "schema_version": "sticker_sheet_v1"}) == "sticker"


def test_detect_packet_review():
    assert detect_subtype({"kind": "forge_packet_review", "schema_version": "packet_review_manifest_v1"}) == "packet_review"


def test_detect_markdown_document():
    assert detect_subtype({"kind": "markdown_document", "schema_version": "document_manifest_v1"}) == "document"


def test_detect_unknown_returns_none():
    assert detect_subtype({"kind": "unknown", "schema_version": "v9"}) is None
    assert detect_subtype({}) is None


def test_is_single_document():
    assert is_single_document({"title": "hello", "body": "world"}) is True
    assert is_single_document({"kind": "composite_bundle"}) is False


def test_class_names():
    assert MANIFEST_CLASS_NAMES["bundle"] == "Composite Bundle"
    assert MANIFEST_CLASS_NAMES["label"] == "Label Run"
    assert MANIFEST_CLASS_NAMES["sticker"] == "Sticker Sheet"


def test_document_and_bundle_reference_schemas_declare_resource_roots():
    for filename in ("document_manifest_v1.yaml", "bundle_manifest_v1.yaml"):
        schema = yaml.safe_load((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        resource_roots = schema["properties"]["resource_roots"]
        assert resource_roots["type"] == "array"
        assert resource_roots["minItems"] == 1
        assert resource_roots["items"]["type"] == "string"
