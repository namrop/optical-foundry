"""A5 — the extent of a work: its prose word count, and that count as English.

Promoted from the Codex 0 build (``colophon_measure.prose_words`` and the spine tool's
``_measure_sources_words`` / ``_round_words`` / ``words_to_english``; promotion map A5).
A colophon that says how long the work is ("drawn down to ninety-four thousand words")
goes stale the first time the work is edited, so the engine measures it at build time.

A manifest asks for it with ``presentation.extent``::

    presentation:
      extent: {enabled: true, round: 1000, form: english}   # form: english | number

The compiler then measures every source the manifest names (the whole work, not one
volume: ``engine.volumes`` measures before it cuts) and sets the ``colophon_words``
variable, which the existing colophon rail substitutes into ``<<COLOPHON_WORDS>>``. A
manifest that sets ``variables.colophon_words`` itself keeps its own value.

What counts (the Codex 0 rules, tuned against its 2026-07-31 volumes to ~0.1%):
frontmatter, HTML comments (edition and ornament markers), fenced code and ``of-image``
blocks, fence and div lines, LaTeX command lines, link and image targets, URLs and
footnote markers and ``<<PLACEHOLDER>>`` build variables are not prose; footnote text and link text are. A LaTeX line counts only
for the visible argument of a command named in ``visible_commands`` (by default the
engine's own ``\\OFChapterOpener``); a profile adds its own (Codex 0:
``CodexOpenerEpigraph``).
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

DEFAULT_VISIBLE_COMMANDS = ("OFChapterOpener",)

_FENCE_OPEN_RE = re.compile(r"^(```+|~~~+)\s*(\{?[^\s}]*)")
_COMMENT_LINE_RE = re.compile(r"^\s*%")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_SPAN_ATTR_RE = re.compile(r"\{[.#][^}]*\}")
_LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?")
_BRACE_RE = re.compile(r"[{}]")
_URL_RE = re.compile(r"https?://\S+")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_FOOTNOTE_REF_RE = re.compile(r"\[\^[^\]]+\](?!:)")
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^[^\]]+\]:\s*")
_HEARTWORD_RE = re.compile(r"\^\[([^\]]+)\]\^\{[^}]*\}")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_PLACEHOLDER_RE = re.compile(r"<<[A-Z0-9_]+>>")
_WORD_RE = re.compile(r"[^\W_]+(?:['’.-][^\W_]+)*", re.UNICODE)

_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


class ExtentError(ValueError):
    pass


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    close = text.find("\n", end + 1)
    return "" if close == -1 else text[close + 1:]


def prose_words(text: str, *, visible_commands: Iterable[str] = DEFAULT_VISIBLE_COMMANDS) -> int:
    """Words a reader receives from one Markdown body (frontmatter already stripped or not)."""
    visible = [re.compile(r"\\" + re.escape(name) + r"\*?(?:\[[^\]]*\])?\{([^}]*)\}") for name in visible_commands]
    text = _HTML_COMMENT_RE.sub(" ", strip_frontmatter(text))
    words = 0
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        opened = _FENCE_OPEN_RE.match(stripped)
        if opened:
            fence = opened.group(1)
            continue
        if not stripped or _COMMENT_LINE_RE.match(line):
            continue
        if stripped.startswith(":::") or re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            continue
        if stripped.startswith("\\"):
            for rx in visible:
                for m in rx.finditer(line):
                    words += len(_WORD_RE.findall(m.group(1)))
            continue
        line = _HEADING_RE.sub("", stripped)
        line = _PLACEHOLDER_RE.sub(" ", line)  # build-time placeholders are not the author's words
        line = _FOOTNOTE_DEF_RE.sub("", line)
        line = _HEARTWORD_RE.sub(r"\1", line)
        line = _SPAN_ATTR_RE.sub(" ", line)
        line = _MD_IMAGE_RE.sub(" ", line)
        line = _MD_LINK_RE.sub(r"\1", line)
        line = _FOOTNOTE_REF_RE.sub(" ", line)
        line = _URL_RE.sub(" ", line)
        line = _LATEX_COMMAND_RE.sub(" ", line)
        line = _BRACE_RE.sub(" ", line)
        words += len(_WORD_RE.findall(line))
    return words


def measure_paths(paths: Iterable[Path], *, visible_commands: Iterable[str] = DEFAULT_VISIBLE_COMMANDS) -> int:
    total = 0
    for path in paths:
        try:
            total += prose_words(Path(path).read_text(encoding="utf-8"), visible_commands=visible_commands)
        except OSError:
            continue
    return total


def round_words(count: int, granularity: int = 1000) -> int:
    if granularity <= 0:
        raise ExtentError("extent.round must be a positive integer")
    return int(round(count / granularity) * granularity)


def words_to_english(count: int) -> str:
    """120000 -> "one hundred twenty thousand"; a million and over stays numeric."""

    def below_thousand(n: int) -> str:
        parts: list[str] = []
        hundreds, rem = divmod(n, 100)
        if hundreds:
            parts.append(f"{_ONES[hundreds]} hundred")
        if rem >= 20:
            tens, ones = divmod(rem, 10)
            parts.append(_TENS[tens] + (f"-{_ONES[ones]}" if ones else ""))
        elif rem:
            parts.append(_ONES[rem])
        return " ".join(parts)

    if count < 0:
        raise ExtentError("a word count cannot be negative")
    if count == 0:
        return "zero"
    if count < 1000:
        return below_thousand(count)
    thousands, rem = divmod(count, 1000)
    if thousands > 999:
        return f"{count:,}"
    phrase = f"{below_thousand(thousands)} thousand"
    if rem:
        phrase += f" {below_thousand(rem)}"
    return phrase


def extent_config(manifest: dict[str, Any]) -> dict[str, Any] | None:
    pres = manifest.get("presentation") if isinstance(manifest.get("presentation"), dict) else {}
    cfg = pres.get("extent")
    if not isinstance(cfg, dict) or not cfg.get("enabled", True):
        return None
    form = cfg.get("form", "english")
    if form not in ("english", "number"):
        raise ExtentError("presentation.extent.form must be english or number")
    return {"round": int(cfg.get("round", 1000)), "form": form,
            "visible_commands": list(cfg.get("visible_commands") or DEFAULT_VISIBLE_COMMANDS)}


def apply_extent(manifest: dict[str, Any], *, base: Path | None = None) -> dict[str, Any] | None:
    """Measure the manifest's sources and set ``variables.colophon_words`` in place.

    Returns the extent record (exact, rounded, printed) or None when not asked for or
    when the manifest already supplies ``colophon_words``.
    """
    cfg = extent_config(manifest)
    if cfg is None:
        return None
    variables = manifest.setdefault("variables", {})
    if not isinstance(variables, dict) or variables.get("colophon_words") is not None:
        return None
    paths = []
    for src in manifest.get("sources") or []:
        raw = src.get("path") if isinstance(src, dict) else None
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute() and base is not None:
            p = base / p
        paths.append(p)
    exact = measure_paths(paths, visible_commands=cfg["visible_commands"])
    rounded = round_words(exact, cfg["round"])
    printed: Any = words_to_english(rounded) if cfg["form"] == "english" else rounded
    variables["colophon_words"] = printed
    return {"exact": exact, "rounded": rounded, "printed": printed, "sources": len(paths)}
