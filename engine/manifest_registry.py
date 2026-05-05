"""Manifest subtype registry.

The registry maps (kind, schema_version) pairs to ManifestCompiler subclasses
and provides lookup/validation entrypoints. New manifest subtypes are added by
registering a compiler here; the rest of the engine routes through the registry.
"""

from __future__ import annotations

from engine.manifest_compiler import ManifestCompiler
from engine.schemas import MANIFEST_SUBTYPES, detect_subtype
from typing import Any


class ManifestRegistry:
    """Central registry for all supported render-manifest subtypes."""

    def __init__(self) -> None:
        self._compilers: dict[str, type[ManifestCompiler]] = {}

    def register(self, kind: str, schema_version: str, compiler_cls: type[ManifestCompiler]) -> None:
        """Register a compiler for a (kind, schema_version) pair."""
        key = self._key(kind, schema_version)
        if key in self._compilers:
            raise KeyError(f"compiler already registered for {key}")
        self._compilers[key] = compiler_cls

    def get_compiler(self, kind: str, schema_version: str) -> type[ManifestCompiler] | None:
        """Return the registered compiler class, or None."""
        return self._compilers.get(self._key(kind, schema_version))

    def resolve_compiler(self, raw: dict[str, Any]) -> type[ManifestCompiler] | None:
        """Resolve the correct compiler for a raw manifest dict."""
        kind = raw.get("kind")
        schema_version = raw.get("schema_version")
        if not kind or not schema_version:
            return None
        return self.get_compiler(kind, schema_version)

    def known_subtypes(self) -> list[tuple[str, str, str]]:
        """List all registered (kind, schema_version, class_name) triples."""
        return [(*self._split_key(k), cls.__name__) for k, cls in self._compilers.items()]

    def supported_kinds(self) -> list[str]:
        """List all supported manifest kind values."""
        # Collect kinds from registered compilers + schema constants.
        registered = set(k[0] for k in self._compilers)
        declared = set(k for (k, _), _ in MANIFEST_SUBTYPES.items())
        return sorted(registered | declared)

    @staticmethod
    def _key(kind: str, schema_version: str) -> str:
        return f"{kind}::{schema_version}"

    @staticmethod
    def _split_key(key: str) -> tuple[str, str]:
        kind, schema_version = key.split("::", 1)
        return kind, schema_version
