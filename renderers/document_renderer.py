"""Single Markdown document renderer.

Takes a Markdown file path, extracts frontmatter for metadata, builds a
minimal ProjectionPlan, and delegates to PandocRenderer.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from engine.profile_resolver import resolve_profile
from engine.page_size import page_margins_from_mapping, page_size_from_mapping, profile_default_page_size
from engine.projection_plan import ProjectionPlan
from engine.report_settings import ReportSettingsError, resolve_report_settings
from engine.manifest_compiler import (
    _document_matter_role,
    _frontmatter_to_markdown,
    _inject_document_matter_command,
    _write_temp_markdown,
)
from renderers.pandoc_renderer import PandocRenderer


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (parsed_frontmatter_dict, body_str). Minimal parser."""
    text = text.lstrip()
    if not text.startswith("---"):
        return {}, text
    idx = text.find("---", 3)
    if idx == -1:
        return {}, text
    try:
        import yaml
        fm = yaml.safe_load(text[3:idx])
        fm = fm if isinstance(fm, dict) else {}
    except (ImportError, Exception):
        fm = {}
    body = text[idx + 3:]
    return fm, body


def _profile_default_toc(profile_id: str) -> bool:
    """Return the single-document TOC default for a profile.

    Letter/stationery profiles are authored artifacts, not reports. They should
    not grow a table of contents unless source frontmatter explicitly asks for
    one.
    """
    try:
        resolved = resolve_profile(profile_id)
    except Exception:
        return True
    return False if resolved.profile_family == "stationery_art" else True


def _settings_error_evidence(render_id: str, message: str) -> dict:
    """Return error evidence for a fatal report-frontmatter validation failure.

    Shaped so the MCP layer (`_distill` / `_embedded_pdf_result`) reports a
    clean error with no PDF, mirroring PandocRenderer._evidence_error.
    """
    return {
        "schema_version": "render_evidence_v1",
        "render_id": render_id,
        "status": "error",
        "error": message,
        "render_metadata": {"success": False, "error": message},
        "validation": {
            "status": "failed",
            "checks": {"pdf_written": False},
            "warning_count": 0,
            "errors": [message],
        },
        "output": {},
        "warnings": [message],
    }


def _profile_default_page_size(profile_id: str) -> tuple[str, str]:
    """Return profile-authored page size default for direct document renders."""

    try:
        return profile_default_page_size(resolve_profile(profile_id).defaults_stack)
    except Exception:
        return "letter", "default"


class DocumentRenderer:
    """Render a single Markdown file through Pandoc."""

    def __init__(self) -> None:
        self._pandoc = PandocRenderer()

    def build_plan(self, source: Path, profile_id: str) -> ProjectionPlan:
        """Build the ProjectionPlan for a direct Markdown document render."""
        text = source.read_text()
        fm, body = _parse_frontmatter(text)

        render_id = fm.get("uid") or source.stem or uuid.uuid4().hex[:12]

        # Resolve + validate the report frontmatter contract. Raises
        # ReportSettingsError on a fatal problem (e.g. unknown classification);
        # render() catches it and returns clean error evidence.
        try:
            canonical_profile_id = resolve_profile(profile_id).canonical_profile_id
        except Exception:
            canonical_profile_id = profile_id
        document_settings, frontmatter_warnings = resolve_report_settings(
            fm, canonical_profile_id=canonical_profile_id
        )

        matter_role = _document_matter_role({}, fm)
        page_size, page_size_source = page_size_from_mapping(fm, scope="source_frontmatter")
        if page_size_source == "default":
            page_size, page_size_source = _profile_default_page_size(profile_id)
        page_margins, page_margins_source = page_margins_from_mapping(fm, scope="source_frontmatter")
        render_source = source
        if matter_role == "frontmatter":
            compiled_body = _inject_document_matter_command(body, matter_role)
            render_source = _write_temp_markdown(
                f"document_{render_id}",
                _frontmatter_to_markdown(fm, compiled_body),
            )

        return ProjectionPlan(
            profile_id=profile_id,
            render_id=render_id,
            render_source=render_source,
            title=fm.get("title", source.stem),
            subtitle=fm.get("subtitle", ""),
            author=fm.get("author", ""),
            date=fm.get("date", ""),
            toc=fm.get("toc", _profile_default_toc(profile_id)),
            toc_depth=fm.get("toc-depth", 3),
            numbersections=fm.get("numbersections", True),
            page_size=page_size,
            page_margins=page_margins,
            document_settings=document_settings,
            source_inventory=[
                {
                    "uid": render_id,
                    "path": str(source),
                    "role": matter_role,
                    "digest_sha256": _sha256_hex(source),
                    "render_lane": "direct_markdown",
                }
            ],
            source_resource_roots=[source.parent.resolve()],
            boundary_assertions={
                "document_manifest_lane": False,
                "manifest_family": "document",
                "assembly_strategy": "direct_markdown",
                "document_matter_role": matter_role,
                "frontmatter_mode_enabled": matter_role == "frontmatter",
                "page_size": page_size,
                "page_size_source": page_size_source,
                "page_margins": page_margins,
                "page_margins_source": page_margins_source,
                # Surface report-frontmatter warnings both into the general
                # warnings channel (keeps warning_count == len(warnings)) and a
                # distinct list the MCP response exposes to network callers.
                "warnings": list(frontmatter_warnings),
                "frontmatter_warnings": list(frontmatter_warnings),
            },
        )

    def render(self, source: Path, profile_id: str, output_dir: str | None = None) -> dict:
        """Render a Markdown document and return evidence."""
        try:
            plan = self.build_plan(source, profile_id)
        except ReportSettingsError as exc:
            render_id = Path(source).stem or "report"
            evidence = _settings_error_evidence(render_id, str(exc))
            if output_dir:
                try:
                    out = Path(output_dir)
                    out.mkdir(parents=True, exist_ok=True)
                    (out / f"{render_id}.evidence.json").write_text(
                        __import__("json").dumps(evidence, indent=2) + "\n"
                    )
                except OSError:
                    pass
            return evidence
        return self._pandoc.render(plan, output_dir=output_dir)
