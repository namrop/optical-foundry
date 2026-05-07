"""Tests for manifest-family resolution and profile/manifest separation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.manifest_resolver import resolve_manifest

GF = Path(__file__).resolve().parents[1]
SRC = GF / "fixtures" / "sources"


def test_packet_review_resolves_as_manifest_family_not_profile_family(tmp_path):
    packet = tmp_path / "packet"
    packet.mkdir()
    (packet / "STATE.json").write_text('{"status":"active"}\n')
    (packet / "PROGRESS.md").write_text("# Progress\n")
    manifest = {
        "kind": "forge_packet_review",
        "schema_version": "packet_review_manifest_v1",
        "profile": "prometheus-packet",
        "packet": {"path": str(packet), "include": ["STATE.json", "PROGRESS.md"]},
        "render": {"assembly_strategy": "combined_markdown"},
    }

    resolved = resolve_manifest(manifest)

    assert resolved.manifest_family == "packet_review"
    assert resolved.manifest_family != "document_spine"
    assert resolved.assembly_strategy == "combined_markdown"
    assert [child.object_id for child in resolved.children] == ["STATE_json", "PROGRESS_md"]
    assert all(child.requested_profile_id == "prometheus-packet" for child in resolved.children)


def test_bundle_longform_preserves_child_profile_requests():
    manifest = {
        "kind": "composite_bundle",
        "schema_version": "bundle_manifest_v1",
        "bundle_id": "profile-axis-test",
        "profile": "generic-report",
        "render": {"assembly_strategy": "combined_markdown"},
        "sources": [
            {"uid": "intro", "path": str(SRC / "source-001.md"), "role": "primary_anchor", "order": 1, "profile_id": "tech"},
            {"uid": "letter", "path": str(SRC / "source-002.md"), "role": "supporting_anchor", "order": 2, "profile_id": "mythic-letter"},
        ],
    }

    resolved = resolve_manifest(manifest)

    assert resolved.manifest_family == "bundle_longform"
    assert resolved.assembly_strategy == "combined_markdown"
    assert [child.requested_profile_id for child in resolved.children] == ["tech", "mythic-letter"]
    assert [child.role for child in resolved.children] == ["primary_anchor", "supporting_anchor"]


def test_physical_sheet_resolves_as_manifest_family():
    manifest = {
        "kind": "label_run",
        "schema_version": "label_run_v1",
        "run_id": "labels",
        "sheet_spec": "avery-5164",
        "profile": "labels-avery-5164",
        "labels": [
            {"slot": 1, "source": str(SRC / "label-001.md")},
            {"slot": 2, "source": str(SRC / "label-002.md")},
        ],
    }

    resolved = resolve_manifest(manifest)

    assert resolved.manifest_family == "physical_sheet"
    assert resolved.assembly_strategy == "content_driven_placeholder"
    assert [child.object_id for child in resolved.children] == ["slot-1", "slot-2"]
    assert all(child.requested_profile_id == "labels-avery-5164" for child in resolved.children)
