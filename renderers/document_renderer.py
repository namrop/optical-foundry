"""Single Markdown document renderer.

Takes a Markdown file path, extracts frontmatter for metadata, builds a
minimal ProjectionPlan, and delegates to PandocRenderer.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from engine.profile_resolver import resolve_profile
from engine.projection_plan import ProjectionPlan
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


class DocumentRenderer:
    """Render a single Markdown file through Pandoc."""

    def __init__(self) -> None:
        self._pandoc = PandocRenderer()

    def render(self, source: Path, profile_id: str, output_dir: str | None = None) -> dict:
        """Render a Markdown document and return evidence."""
        text = source.read_text()
        fm, _body = _parse_frontmatter(text)

        render_id = fm.get("uid") or source.stem or uuid.uuid4().hex[:12]

        plan = ProjectionPlan(
            profile_id=profile_id,
            render_id=render_id,
            render_source=source,
            title=fm.get("title", source.stem),
            subtitle=fm.get("subtitle", ""),
            author=fm.get("author", ""),
            date=fm.get("date", ""),
            toc=fm.get("toc", _profile_default_toc(profile_id)),
            toc_depth=fm.get("toc-depth", 3),
            numbersections=fm.get("numbersections", True),
            source_inventory=[
                {"uid": render_id, "path": str(source), "digest_sha256": _sha256_hex(source)}
            ],
        )
        return self._pandoc.render(plan, output_dir=output_dir)
