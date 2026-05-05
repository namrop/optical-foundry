"""Shared schema constants and version anchor for Optical Foundry.

This module holds the canonical SCHEMA_VERSION and a lightweight validator
for the manifest envelope. Production-safe parsing belongs in the manifest
compiler; this module provides detection and fast-fail guards.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "v1"

# Supported manifest (kind, schema_version) pairs.
MANIFEST_SUBTYPES: dict[tuple[str, str], str] = {
    ("composite_bundle", "bundle_manifest_v1"): "bundle",
    ("cam_stack", "bundle_manifest_v1"): "bundle",
    ("codex_bundle", "bundle_manifest_v1"): "bundle",
    ("label_run", "label_run_v1"): "label",
    ("sticker_sheet", "sticker_sheet_v1"): "sticker",
    ("forge_packet_review", "packet_review_manifest_v1"): "packet_review",
}

# Maps subclass to canonical display name.
MANIFEST_CLASS_NAMES: dict[str, str] = {
    "bundle": "Composite Bundle",
    "label": "Label Run",
    "sticker": "Sticker Sheet",
    "packet_review": "Forge Packet Review",
    "document": "Markdown Document",
}


def detect_subtype(raw: dict[str, Any]) -> str | None:
    """Return the manifest class name or None if the envelope is unrecognised."""
    kind = raw.get("kind")
    schema_version = raw.get("schema_version")
    if not kind or not schema_version:
        return None
    return MANIFEST_SUBTYPES.get((kind, schema_version))


def is_single_document(raw: dict[str, Any]) -> bool:
    """True when the input is a Markdown document, not a manifest."""
    return "kind" not in raw and "schema_version" not in raw
