"""Frontmatter-driven epigraphs.

Any source may carry an epigraph in its YAML frontmatter; the engine harvests it
and the profile decides how it sets. Promoted from the Codex 0 book compiler
(``_read_divider_epigraph``, 2026-09-28).

Fields (only ``epigraph_line`` is required; without it there is no epigraph and
the opener is a bare heading, which is what keeps unauthored sources silent):

- ``epigraph_line`` -> ``text``: the quoted line
- ``epigraph_speaker`` -> ``speaker``: dramatic line, who says it
- ``epigraph_context`` -> ``context``: dramatic line, the circumstance
- ``epigraph_author`` -> ``author``: bibliographic line, who wrote the work
- ``epigraph_source`` -> ``source``: bibliographic line, the work
- ``epigraph_translator`` -> ``translator``: bibliographic line, ``tr. Name``;
  the slot goes blank when absent
- ``epigraph_date`` -> ``date``: when the WORK was authored
- ``epigraph_register`` -> ``register``: ``witness`` sets the body upright;
  anything else is literary (italic)

``epigraph_date`` carries one meaning across every entry: when the work was
authored, not when this translation or edition appeared. That is why the
translator slot exists — before it did, the date quietly switched to the year of
translation on exactly the entries that folded a translator into the title.

The harvested mapping is what ``chapter_opener.epigraph`` accepts, lowered through
the layered ``\\CodexOpenerEpigraph`` grammar (ratified 2026-07-28).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

EPIGRAPH_FIELDS: tuple[tuple[str, str], ...] = (
    ("epigraph_speaker", "speaker"),
    ("epigraph_context", "context"),
    ("epigraph_author", "author"),
    ("epigraph_source", "source"),
    ("epigraph_translator", "translator"),
    ("epigraph_date", "date"),
    ("epigraph_register", "register"),
)


def epigraph_from_frontmatter(frontmatter: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the structured epigraph a frontmatter mapping carries, or None."""
    if not isinstance(frontmatter, Mapping):
        return None
    line = str(frontmatter.get("epigraph_line") or "").strip()
    if not line:
        return None
    epigraph: dict[str, Any] = {"text": line}
    for src_key, dst_key in EPIGRAPH_FIELDS:
        val = frontmatter.get(src_key)
        if val is not None and str(val).strip():
            epigraph[dst_key] = str(val).strip()
    return epigraph


def epigraph_from_file(path: Path) -> dict[str, Any] | None:
    """Harvest the epigraph from a Markdown file's frontmatter.

    An unreadable file, a file without frontmatter, and frontmatter without
    ``epigraph_line`` all return None.
    """
    from engine.manifest_compiler import _split_frontmatter_and_body

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    fm, _body = _split_frontmatter_and_body(text)
    return epigraph_from_frontmatter(fm)
