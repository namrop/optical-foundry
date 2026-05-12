"""Manifest envelope and subtype validator.

Phase 0: validates the render-manifest envelope shape and runs subtype-specific
checks before a compiler is invoked.
"""

from __future__ import annotations

from typing import Any

from engine.schemas import MANIFEST_SUBTYPES, detect_subtype

# Required keys every render manifest must carry.
ENVELOPE_REQUIRED = {"kind", "schema_version", "profile"}

# Known values (from schema definitions).
KNOWN_KINDS = {
    "composite_bundle",
    "cam_stack",
    "codex_bundle",
    "markdown_document",
    "label_run",
    "sticker_sheet",
    "forge_packet_review",
}
KNOWN_SCHEMA_VERSIONS = {
    "bundle_manifest_v1",
    "document_manifest_v1",
    "label_run_v1",
    "sticker_sheet_v1",
    "packet_review_manifest_v1",
}


def validate_manifest_envelope(raw: dict[str, Any]) -> list[str]:
    """Validate the top-level render-manifest envelope.

    Returns a list of error strings; empty list means valid.
    """
    errors: list[str] = []

    if not isinstance(raw, dict):
        return ["manifest is not a dict"]

    missing = ENVELOPE_REQUIRED - set(raw.keys())
    if missing:
        errors.append(f"missing required envelope keys: {sorted(missing)}")

    kind = raw.get("kind")
    if kind is not None and kind not in KNOWN_KINDS:
        errors.append(f"unknown manifest kind: {kind}")

    schema_version = raw.get("schema_version")
    if schema_version is not None and schema_version not in KNOWN_SCHEMA_VERSIONS:
        errors.append(f"unknown schema_version: {schema_version}")

    if kind is not None and schema_version is not None:
        if (kind, schema_version) not in MANIFEST_SUBTYPES:
            errors.append(f"no compiler registered for (kind={kind}, schema_version={schema_version})")

    profile = raw.get("profile")
    if not isinstance(profile, str) or not profile.strip():
        errors.append("profile must be a non-empty string")

    return errors


def validate_manifest_subtype(raw: dict[str, Any]) -> list[str]:
    """Run subtype-specific validation on top of envelope validation.

    Phase 0: delegates to envelope checks only. Subtype-specific checks
    become active when compilers are registered.
    """
    errors = validate_manifest_envelope(raw)
    if errors:
        return errors

    # Subtype-compiler-specific validation will be dispatched here in later phases.
    return []
