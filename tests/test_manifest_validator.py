"""Tests for validators.manifest_validator — envelope and subtype validation."""
from validators.manifest_validator import validate_manifest_envelope, validate_manifest_subtype


def test_valid_bundle_envelope():
    errors = validate_manifest_envelope({"kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "profile": "cam"})
    assert errors == []


def test_valid_markdown_document_envelope():
    errors = validate_manifest_envelope({"kind": "markdown_document", "schema_version": "document_manifest_v1", "profile": "generic-report"})
    assert errors == []


def test_missing_keys():
    errors = validate_manifest_envelope({"kind": "composite_bundle"})
    assert len(errors) >= 1
    assert any("schema_version" in e for e in errors)


def test_unknown_kind():
    errors = validate_manifest_envelope({"kind": "bogus", "schema_version": "bundle_manifest_v1", "profile": "x"})
    assert any("unknown manifest kind" in e for e in errors)


def test_unknown_schema_version():
    errors = validate_manifest_envelope({"kind": "composite_bundle", "schema_version": "bogus_v99", "profile": "x"})
    assert any("unknown schema_version" in e for e in errors)


def test_unregistered_pair():
    errors = validate_manifest_envelope({"kind": "label_run", "schema_version": "packet_review_manifest_v1", "profile": "x"})
    assert any("no compiler registered" in e for e in errors)


def test_empty_profile():
    errors = validate_manifest_envelope({"kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "profile": ""})
    assert any("profile" in e for e in errors)


def test_not_dict():
    errors = validate_manifest_envelope([])
    assert any("not a dict" in e for e in errors)


def test_valid_subtype_passes():
    errors = validate_manifest_subtype({"kind": "composite_bundle", "schema_version": "bundle_manifest_v1", "profile": "cam"})
    assert errors == []
