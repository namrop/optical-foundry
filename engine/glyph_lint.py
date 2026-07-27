"""Detect missing-character warnings emitted by LaTeX/Pandoc renders.

Pandoc surfaces LuaLaTeX's ``Missing character`` warnings on stderr while still
returning exit code 0. The generated PDF text layer represents those lost glyphs
as U+FFFD, so the compile warning supplies the original codepoint and the
form-feed-delimited ``pdftotext`` extract supplies the physical PDF page.
"""
from __future__ import annotations

from collections import OrderedDict
import re
from typing import Any


_MISSING_CHARACTER_RE = re.compile(
    r"Missing character:\s+There is no\s+(?P<char>.*?)\s+"
    r"\((?P<codepoint>U\+[0-9A-Fa-f]{4,6})\)"
)


def scan_missing_character_warnings(log_text: str, text_extract: str) -> list[dict[str, Any]]:
    """Return normalized missing-glyph failures from a compile log.

    LuaLaTeX may emit the same warning once per compile pass. Results therefore
    deduplicate by codepoint while retaining ``warning_count``. Page numbers are
    physical PDF pages (1-based), recovered from form-feed-separated pdftotext
    output. When several codepoints are missing in one render, every page carrying
    a replacement character is conservatively reported for each codepoint rather
    than inventing a false one-to-one mapping.
    """

    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for match in _MISSING_CHARACTER_RE.finditer(log_text or ""):
        codepoint = match.group("codepoint").upper()
        character = match.group("char").strip()
        entry = grouped.setdefault(
            codepoint,
            {
                "character": character,
                "codepoint": codepoint,
                "pdf_pages": [],
                "warning_count": 0,
            },
        )
        entry["warning_count"] += 1

    if not grouped:
        return []

    pages = (text_extract or "").split("\f")
    replacement_pages = {
        page_number
        for page_number, page_text in enumerate(pages, start=1)
        if "\ufffd" in page_text
    }
    for entry in grouped.values():
        character = str(entry["character"])
        character_pages = {
            page_number
            for page_number, page_text in enumerate(pages, start=1)
            if character and character in page_text
        }
        entry["pdf_pages"] = sorted(replacement_pages | character_pages)

    return list(grouped.values())


def format_missing_character_failures(failures: list[dict[str, Any]]) -> str:
    """Format failures for a human-visible render error."""

    formatted: list[str] = []
    for failure in failures:
        codepoint = str(failure.get("codepoint") or "unknown codepoint")
        character = str(failure.get("character") or "").strip()
        pages = [int(page) for page in failure.get("pdf_pages", [])]
        warning_count = int(failure.get("warning_count", 0))

        glyph_label = f"{codepoint} {character}".strip()
        if pages:
            page_label = "PDF page" if len(pages) == 1 else "PDF pages"
            page_text = ", ".join(str(page) for page in pages)
            location = f"{page_label} {page_text}"
        else:
            location = "PDF page unknown"
        warning_label = "compile warning" if warning_count == 1 else "compile warnings"
        formatted.append(f"{glyph_label} on {location} ({warning_count} {warning_label})")

    return "; ".join(formatted)
