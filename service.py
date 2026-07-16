"""Optical Foundry render service facade.

Single entry surface shared by the CLI and the MCP server so the two never
drift. This intentionally reuses the existing CLI orchestration helpers
(`_parse_yaml_file`, `_default_registry`) rather than duplicating them.

Scope note: this is the *thin* facade added alongside the MCP scaffold. The
larger data-driven-profile-registry + packaging refactor is deliberately
deferred (see README / architecture notes).
"""
from __future__ import annotations

from pathlib import Path

from renderers.document_renderer import DocumentRenderer
from renderers.pandoc_renderer import PandocRenderer
from cli import _parse_yaml_file, _default_registry


def render_document(source: str | Path, profile: str, output_dir: str | None = None) -> dict:
    """Render one Markdown source through a profile. Returns the evidence dict."""
    return DocumentRenderer().render(Path(source), profile, output_dir=output_dir)


def render_manifest(manifest_path: str | Path, output_dir: str | None = None) -> dict:
    """Compile and render a typed manifest. Returns the evidence dict.

    Raises ValueError on unknown manifest kind or validation failure so callers
    (CLI, MCP) can surface a clean error instead of a half-rendered artifact.
    """
    manifest_path = Path(manifest_path)
    raw = _parse_yaml_file(manifest_path)

    reg = _default_registry()
    compiler_cls = reg.resolve_compiler(raw)
    if compiler_cls is None:
        raise ValueError(
            f"no compiler for kind={raw.get('kind')} schema_version={raw.get('schema_version')}"
        )

    compiler = compiler_cls()
    errors = compiler.validate(raw)
    if errors:
        raise ValueError("manifest validation failed: " + "; ".join(errors))

    plan = compiler.compile(raw)
    return PandocRenderer().render(plan, output_dir=output_dir)
