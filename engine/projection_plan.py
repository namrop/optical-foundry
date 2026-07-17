"""ProjectionPlan — the internal compiled render intermediate representation.

A ProjectionPlan is produced by compiling a Markdown document or a typed render
manifest through a ManifestCompiler. It carries everything the render dispatch
needs to execute a Pandoc render: profile reference, source inventory, Pandoc
defaults overlay, template/style selections, and render metadata.

AssemblyView is an optional structured sub-object that records how a
multi-source or multi-layout compilation was assembled. Renderers that need
assembly provenance should populate it; simple single-document renders may
leave it empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from engine.schemas import SCHEMA_VERSION

if TYPE_CHECKING:
    from engine.report_settings import ReportSettings


@dataclass
class AssemblyView:
    """Structured assembly record for multi-source / multi-layout renders."""

    assembly_kind: str  # manifest kind (composite_bundle, label_run, etc.)
    schema_version: str = SCHEMA_VERSION
    manifest_family: str = ""
    manifest_subtype: str = ""
    assembly_strategy: str = ""
    numbering_strategy: str = ""
    assembly_title: str = ""
    assembly_subtitle: str = ""
    source_order: list[str] = field(default_factory=list)  # ordered UIDs
    source_paths: dict[str, str] = field(default_factory=dict)  # UID → path
    source_roles: dict[str, str] = field(default_factory=dict)  # UID → role
    source_digests: dict[str, str] = field(default_factory=dict)  # UID → sha256
    child_profiles: list[dict[str, Any]] = field(default_factory=list)
    generated_sections: list[str] = field(default_factory=list)
    figure_slots: list[str] = field(default_factory=list)


@dataclass
class ProjectionPlan:
    """Compiled render plan ready for execution by the render dispatch.

    A ProjectionPlan is immutable by convention once created. Render dispatch
    reads it and passes it to the appropriate renderer.
    """

    profile_id: str

    # Unique render identity for evidence tracing.
    render_id: str  # e.g. uuid4 hex or timestamp-based slug

    # The primary Markdown source that Pandoc will consume.
    # For single-document renders this is the input file.
    # For manifests this is the assembled Markdown product of the compiler.
    render_source: Path

    # Pandoc defaults overlay dict (maps to --defaults YAML), if any.
    pandoc_defaults_overlay: dict[str, Any] | None = None

    # LaTeX template filename (relative)
    template: str | None = None

    # LaTeX style package (without .sty); loaded by template.
    style: str | None = None

    # Evidence-friendly metadata.
    title: str = ""
    subtitle: str = ""
    author: str = ""
    date: str = ""
    toc: bool = True
    toc_depth: int = 3
    numbersections: bool = True
    output_format: str = "pdf"
    output_extension: str = ".pdf"
    page_size: str = "letter"
    page_margins: list[str] = field(default_factory=list)
    orientation: str = "portrait"

    # Source inventory for evidence sidecars.
    source_inventory: list[dict[str, Any]] = field(default_factory=list)

    # Figure inventory.
    figure_inventory: list[dict[str, Any]] = field(default_factory=list)

    # Directories that authored source-relative resources should resolve from.
    # Manifest compilers may emit temporary assembled Markdown; this preserves
    # source-local image roots for raw LaTeX / layout-image asset lookup.
    source_resource_roots: list[Path] = field(default_factory=list)

    # Manifest-owned delivery/use-context controls. Profiles remain visual /
    # semantic identity; delivery records physical output requirements such as
    # bound geometry, page-number strategy, and colophon behavior.
    delivery: dict[str, Any] = field(default_factory=lambda: {"mode": "screen"})

    # Resolved report-frontmatter contract (classification, cover metadata,
    # figure caption/numbering, footers, PDF metadata, artifact name). Populated
    # for direct-document renders; None for manifest/legacy lanes.
    document_settings: "ReportSettings | None" = None

    # Optionally filled for multi-source renders.
    assembly: AssemblyView | None = None

    # Validation / boundary assertions.
    boundary_assertions: dict[str, Any] = field(default_factory=dict)

    @property
    def has_assembly(self) -> bool:
        return self.assembly is not None and len(self.assembly.source_order) > 0
