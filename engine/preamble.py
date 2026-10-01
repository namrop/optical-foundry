"""One preamble per render: every line the engine adds to the LaTeX preamble.

Why this exists (architecture review 2026-10-01, candidate 2; ruling
01a0f8ba-4937). Preamble lines used to reach LaTeX by three routes: the render
source's frontmatter ``header-includes``, ``header-includes`` variables in the
page-geometry and font-fallback defaults overlays, and ``--include-in-header``
files (strikeout, draft, image bake). Pandoc keeps only one of the first two —
the last defaults file that sets the variable wins, and metadata is dropped
whenever any variable or include file is given — so each overlay had to copy
the source's lines forward, and a render with an include file but neither
overlay lost them.

Now every contributor hands its lines to a ``Preamble``, which writes them as
the render's single ``--include-in-header`` file. Lines are emitted in a fixed
order of origin (``ORIGINS``), not call order, and the first copy of a repeated
line wins. The source's own frontmatter ``header-includes`` are one origin;
pandoc drops the metadata copy because the include file is given.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Iterable

import yaml

# Emission order. Earlier origins are emitted first.
ORIGINS: tuple[str, ...] = (
    "source",          # the render source's frontmatter header-includes (preprocessors write here)
    "page_geometry",   # physical page size special
    "bound_delivery",  # bound pagestyles, illumination rails
    "font_fallback",   # host font substitution for the yugen style family
    "strikeout",       # soul / lua-ul when the source has ~~text~~
    "draft",           # graphicx draft mode
    "image_bake",      # the lossless image-bake callback
)


@dataclass
class Preamble:
    """The preamble lines of one render, by origin."""

    _lines: dict[str, list[str]] = field(default_factory=lambda: {origin: [] for origin in ORIGINS})

    def add(self, origin: str, lines: Iterable[str] | str) -> None:
        if origin not in self._lines:
            raise ValueError(f"unknown preamble origin {origin!r}; known: {', '.join(ORIGINS)}")
        if isinstance(lines, str):
            lines = [lines]
        self._lines[origin].extend(str(line) for line in lines if str(line).strip())

    def add_source(self, render_source: Path) -> None:
        """Take the source's frontmatter ``header-includes``."""
        self.add("source", source_header_includes(render_source))

    def lines(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for origin in ORIGINS:
            for line in self._lines[origin]:
                if line not in seen:
                    seen.add(line)
                    out.append(line)
        return out

    def text(self) -> str:
        lines = self.lines()
        return "\n".join(lines) + "\n" if lines else ""

    def write(self, out_dir: Path, render_id: str) -> Path | None:
        """Write the include file; ``None`` when there is nothing to include."""
        text = self.text()
        if not text:
            return None
        path = Path(out_dir) / f"{render_id}.preamble.tex"
        path.write_text(text, encoding="utf-8")
        return path

    def evidence(self, path: Path | None) -> dict[str, Any]:
        text = self.text()
        return {
            "path": str(path) if path else "",
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
            "lines_by_origin": {origin: len(lines) for origin, lines in self._lines.items() if lines},
        }


def source_header_includes(render_source: Path) -> list[str]:
    """The frontmatter ``header-includes`` (or ``header_includes``) of a Markdown file."""
    render_source = Path(render_source)
    if not render_source.exists():
        return []
    text = render_source.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---", 4)
    if end == -1:
        return []
    try:
        frontmatter = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(frontmatter, dict):
        return []
    includes = frontmatter.get("header-includes") or frontmatter.get("header_includes")
    if includes is None:
        return []
    if isinstance(includes, list):
        return [str(item) for item in includes if item]
    return [str(includes)] if includes else []
