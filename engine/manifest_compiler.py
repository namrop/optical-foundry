"""Manifest compiler base and concrete compilers.

A ManifestCompiler validates a typed render manifest and produces a
ProjectionPlan. Each supported (kind, schema_version) pair should have one
dedicated compiler registered through the ManifestRegistry.

Concrete compilers for bundle, label, sticker, and packet-review manifests
will be added here as implementations mature. For Phase 0 we provide the base
class and a single-document identity compiler used when the input is a
Markdown document rather than a manifest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.projection_plan import ProjectionPlan


class ManifestCompiler(ABC):
    """Base for all manifest compilers.

    Subclasses must define `compile` and `validate`.
    """

    kind: str = ""
    schema_version: str = ""

    @abstractmethod
    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        """Validate the manifest and produce a ProjectionPlan."""

    @abstractmethod
    def validate(self, manifest: dict[str, Any]) -> list[str]:
        """Return a list of validation errors (empty = valid)."""


class NullCompiler(ManifestCompiler):
    """Identity compiler used when the input is a plain Markdown document.

    This compiler exists so the render dispatch can treat Markdown documents
    as a degenerate manifest case without special-casing the dispatch path.
    """

    kind = "_document"
    schema_version = "_document_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        # Not called for documents — dispatch bypasses this path.
        raise NotImplementedError("NullCompiler is a bypass marker, not an executable compiler")

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        return []


# Module-level singleton for the identity bypass.
null_compiler = NullCompiler()
