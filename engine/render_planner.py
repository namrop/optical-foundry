"""Render planner seam joining profile and manifest axes.

The planner does not execute Pandoc. It turns a single document request or an
assembled manifest request into explicit child render plans plus, when relevant,
a manifest-owned assembly plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.manifest_resolver import ResolvedManifest, ManifestChildSpec, resolve_manifest
from engine.profile_resolver import ResolvedProfile, resolve_profile


@dataclass(frozen=True)
class ChildRenderPlan:
    object_id: str
    source_path: Path | None
    role: str
    requested_profile_id: str | None
    requested_profile_family: str | None
    resolved_profile: ResolvedProfile
    order: int = 0


@dataclass(frozen=True)
class AssemblyPlan:
    manifest_family: str
    strategy: str
    numbering_strategy: str


@dataclass(frozen=True)
class RenderPlan:
    kind: str
    children: list[ChildRenderPlan]
    manifest: ResolvedManifest | None = None
    assembly: AssemblyPlan | None = None


def plan_document_render(source_path: str | Path, profile_id: str) -> RenderPlan:
    """Plan one standalone document/object render."""

    resolved = resolve_profile(profile_id)
    child = ChildRenderPlan(
        object_id=Path(source_path).stem,
        source_path=Path(source_path),
        role="document",
        requested_profile_id=profile_id,
        requested_profile_family=None,
        resolved_profile=resolved,
        order=1,
    )
    return RenderPlan(kind="document", children=[child], manifest=None, assembly=None)


def plan_manifest_render(manifest: dict[str, Any]) -> RenderPlan:
    """Plan an assembled manifest render with per-child profile resolution."""

    resolved_manifest = resolve_manifest(manifest)
    children = [_plan_child(child) for child in resolved_manifest.children]
    assembly = AssemblyPlan(
        manifest_family=resolved_manifest.manifest_family,
        strategy=resolved_manifest.assembly_strategy,
        numbering_strategy=resolved_manifest.numbering_strategy,
    )
    return RenderPlan(kind="manifest", children=children, manifest=resolved_manifest, assembly=assembly)


def _plan_child(child: ManifestChildSpec) -> ChildRenderPlan:
    profile_id = child.requested_profile_id or _default_profile_for_family(child.requested_profile_family)
    resolved = resolve_profile(profile_id)
    if child.requested_profile_family and resolved.profile_family != child.requested_profile_family:
        raise ValueError(
            f"child {child.object_id} requested profile_family={child.requested_profile_family}, "
            f"but {profile_id} resolves to {resolved.profile_family}"
        )
    return ChildRenderPlan(
        object_id=child.object_id,
        source_path=child.source_path,
        role=child.role,
        requested_profile_id=child.requested_profile_id,
        requested_profile_family=child.requested_profile_family,
        resolved_profile=resolved,
        order=child.order,
    )


def _default_profile_for_family(profile_family: str | None) -> str:
    defaults = {
        None: "document-spine",
        "document_spine": "document-spine",
        "stationery_art": "mythic-letter",
        "resume": "resume",
        "campaign_art": "elian-packet",
        "physical_sheet_profile": "labels-avery-5164",
    }
    return defaults.get(profile_family, "generic-report")
