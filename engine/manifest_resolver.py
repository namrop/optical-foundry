"""Manifest-family resolver for assembled Optical Foundry artifacts.

Profiles describe individual document/object rendering. Manifests describe
assembled render targets. This resolver keeps those axes separate by compiling
manifest envelopes into a manifest-family record plus child profile requests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ManifestChildSpec:
    object_id: str
    source_path: Path | None
    role: str
    requested_profile_id: str | None = None
    requested_profile_family: str | None = None
    order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedManifest:
    kind: str
    schema_version: str
    manifest_family: str
    manifest_subtype: str
    assembly_strategy: str
    numbering_strategy: str
    children: list[ManifestChildSpec]
    boundary: dict[str, Any] = field(default_factory=dict)


KIND_TO_FAMILY = {
    "composite_bundle": "bundle_longform",
    "forge_packet_review": "packet_review",
    "label_run": "physical_sheet",
    "sticker_sheet": "physical_sheet",
    "campaign_packet": "campaign_packet",
}

DEFAULT_ASSEMBLY_STRATEGY = {
    "bundle_longform": "combined_markdown",
    "packet_review": "combined_markdown",
    "physical_sheet": "content_driven_placeholder",
    "campaign_packet": "pdf_stitch",
}


def resolve_manifest(manifest: dict[str, Any]) -> ResolvedManifest:
    """Resolve manifest family/subtype and child profile requests."""

    if not isinstance(manifest, dict):
        raise TypeError("manifest must be a dict")

    kind = str(manifest.get("kind", ""))
    schema_version = str(manifest.get("schema_version", ""))
    manifest_family = KIND_TO_FAMILY.get(kind, kind or "unknown")
    render_cfg = manifest.get("render", {}) if isinstance(manifest.get("render", {}), dict) else {}
    assembly_strategy = str(
        render_cfg.get("assembly_strategy")
        or manifest.get("assembly_strategy")
        or DEFAULT_ASSEMBLY_STRATEGY.get(manifest_family, "combined_markdown")
    )
    numbering_strategy = str(render_cfg.get("numbering_strategy") or render_cfg.get("numbering") or "continuous")

    children = _children_for_manifest(manifest, manifest_family)

    return ResolvedManifest(
        kind=kind,
        schema_version=schema_version,
        manifest_family=manifest_family,
        manifest_subtype=kind,
        assembly_strategy=assembly_strategy,
        numbering_strategy=numbering_strategy,
        children=children,
        boundary={
            "target_40_latex_mutated": False,
            "profile_manifest_axes_separate": True,
        },
    )


def _children_for_manifest(manifest: dict[str, Any], manifest_family: str) -> list[ManifestChildSpec]:
    if manifest_family == "bundle_longform":
        return _bundle_children(manifest)
    if manifest_family == "packet_review":
        return _packet_review_children(manifest)
    if manifest.get("kind") == "label_run":
        return _label_run_children(manifest)
    if manifest.get("kind") == "sticker_sheet":
        return _sticker_sheet_children(manifest)
    return []


def _default_child_profile(manifest: dict[str, Any]) -> str | None:
    defaults = manifest.get("defaults", {}) if isinstance(manifest.get("defaults", {}), dict) else {}
    return defaults.get("child_profile") or manifest.get("profile")


def _bundle_children(manifest: dict[str, Any]) -> list[ManifestChildSpec]:
    default_profile = _default_child_profile(manifest)
    children: list[ManifestChildSpec] = []
    for src in sorted(manifest.get("sources", []), key=lambda s: s.get("order", 9999)):
        uid = str(src.get("uid", ""))
        children.append(
            ManifestChildSpec(
                object_id=uid,
                source_path=Path(src["path"]) if src.get("path") else None,
                role=str(src.get("role", "source")),
                requested_profile_id=src.get("profile_id") or src.get("profile") or default_profile,
                requested_profile_family=src.get("profile_family"),
                order=int(src.get("order", len(children) + 1)),
                metadata={k: v for k, v in src.items() if k not in {"uid", "path", "role", "profile_id", "profile", "profile_family", "order"}},
            )
        )
    return children


def _packet_review_children(manifest: dict[str, Any]) -> list[ManifestChildSpec]:
    profile = _default_child_profile(manifest)
    pkt = manifest.get("packet", {}) if isinstance(manifest.get("packet", {}), dict) else {}
    render_cfg = manifest.get("render", {}) if isinstance(manifest.get("render", {}), dict) else {}
    pkt_path = Path(pkt.get("path", "")) if pkt.get("path") else None
    includes = pkt.get("include") or ["GOAL.md", "CONSTRAINTS.md", "PLAN.md", "STATE.json", "PROGRESS.md", "VALIDATION.md"]
    children: list[ManifestChildSpec] = []
    for idx, inc_name in enumerate(includes, start=1):
        source = pkt_path / inc_name if pkt_path else None
        children.append(
            ManifestChildSpec(
                object_id=_object_id_from_name(str(inc_name)),
                source_path=source,
                role="packet_surface",
                requested_profile_id=profile,
                order=idx,
            )
        )

    next_order = len(children) + 1
    if render_cfg.get("include_questions", True) and pkt_path and (pkt_path / "QUESTIONS.md").exists():
        children.append(
            ManifestChildSpec(
                object_id="QUESTIONS_md",
                source_path=pkt_path / "QUESTIONS.md",
                role="packet_surface",
                requested_profile_id=profile,
                order=next_order,
            )
        )
        next_order += 1
    if render_cfg.get("include_dirty_state_summary", True) and pkt_path and (pkt_path / "DIRTY_STATE.json").exists():
        children.append(
            ManifestChildSpec(
                object_id="DIRTY_STATE_json",
                source_path=pkt_path / "DIRTY_STATE.json",
                role="packet_surface",
                requested_profile_id=profile,
                order=next_order,
            )
        )
    return children


def _label_run_children(manifest: dict[str, Any]) -> list[ManifestChildSpec]:
    profile = _default_child_profile(manifest)
    children: list[ManifestChildSpec] = []
    for lbl in sorted(manifest.get("labels", []), key=lambda l: l.get("slot", 9999)):
        slot = int(lbl.get("slot", len(children) + 1))
        children.append(
            ManifestChildSpec(
                object_id=f"slot-{slot}",
                source_path=Path(lbl["source"]) if lbl.get("source") else None,
                role="label",
                requested_profile_id=lbl.get("profile_id") or profile,
                requested_profile_family=lbl.get("profile_family"),
                order=slot,
                metadata={"slot": slot},
            )
        )
    return children


def _sticker_sheet_children(manifest: dict[str, Any]) -> list[ManifestChildSpec]:
    profile = _default_child_profile(manifest)
    children: list[ManifestChildSpec] = []
    for idx, cell in enumerate(manifest.get("cells", []), start=1):
        pos = cell.get("position", [idx - 1, 0])
        object_id = f"cell-{pos[0]}-{pos[1]}" if isinstance(pos, list) and len(pos) >= 2 else f"cell-{idx}"
        children.append(
            ManifestChildSpec(
                object_id=object_id,
                source_path=Path(cell["source"]) if cell.get("source") else None,
                role="sticker_cell",
                requested_profile_id=cell.get("profile_id") or profile,
                requested_profile_family=cell.get("profile_family"),
                order=idx,
                metadata={"position": pos},
            )
        )
    return children


def _object_id_from_name(name: str) -> str:
    return name.replace(".", "_").replace("/", "_")
