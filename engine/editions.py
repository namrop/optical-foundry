"""Editions: one source, several audience versions (promotion map C1, C2).

Generalized 2026-10-03 from engine/codex_editions.py (ruling 01a100da-3cde). A profile
declares editions in its spec or package (``editions: {labels: [...]}``) and the marker
namespace its sources use (``markers: {prefix: cx0}``, engine/markers.py); a manifest or
source picks the edition (``edition:`` or Codex 0's ``codex_edition:``). A profile that
declares no editions refuses sources that carry edition markers (fail closed). Codex 0 is
the first adapter; the names below still say "codex" for it, and engine/codex_editions.py
re-exports them.

Original description (Codex 0, prefix cx0):

Preprocess Codex 0 inline edition variants before Pandoc.

Codex 0 keeps edition-specific prose side-by-side in the Markdown source using
HTML comment sentinels so the manuscript remains readable/editable as prose.

Model (2026-07-04): the body before the first `cx0:edition` marker is the
**archival base** — it is used for every edition unless a tagged override
replaces it. Each `cx0:edition` marker carries one or more comma-separated
edition labels (a block may belong to several editions at once) and, for those
editions, swaps in at that place for the archival base. If the archival base is
empty, a tagged block is an **addition** (present only in its tagged editions),
not a replacement.

    <!-- cx0:variant id="how-you-arrived-010" -->
    Archival/raw prose (all editions unless overridden).
    <!-- cx0:edition witness,reader -->
    Veiled prose swapped in for the witness and reader editions.
    <!-- cx0:endvariant -->

The region closes with either `<!-- cx0:endvariant -->` or `<!-- /cx0:variant -->`.

This preprocessor selects one edition before the existing Optical Foundry source
preprocessors run. That ordering keeps inactive `of-image`, Mermaid, Vega, D2,
and Graphviz blocks out of downstream preprocessors.

Note: the archival base is the universal fallback, so an edition with no matching
override inherits the raw base. Regions that must be veiled for a wider edition
therefore require an explicit override for that edition; a missing override does
not fail the render, it inherits the raw base.

To restore fail-closed exposure for a sensitive region, mark the variant with a
`guard` attribute listing the editions that must not inherit the raw base:

    <!-- cx0:variant id="the-reckoning" guard="witness,reader" -->
    Raw archival prose.
    <!-- cx0:edition witness -->
    Veiled witness prose.
    <!-- cx0:endvariant -->

Here rendering the reader edition fails hard (it has no override and is guarded),
while the witness edition renders its override and the archival edition renders
the raw base.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re


class CodexEditionRenderError(RuntimeError):
    """Raised when Codex 0 edition sentinels are malformed or unsafe."""


@dataclass(frozen=True)
class CodexEditionPreprocessResult:
    changed: bool
    rewritten_source: Path
    edition: str = ""
    variant_count: int = 0
    selected_count: int = 0
    fallback_count: int = 0
    editorial_callouts_stripped: int = 0
    editorial_callouts_formatted: int = 0
    selected_variant_ids: list[str] = field(default_factory=list)
    fallback_variant_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


from engine.markers import edition_marker_re

_MARKER_RE = edition_marker_re("cx0")
_ATTR_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)=(?P<quote>[\"'])(?P<value>.*?)(?P=quote)")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_CALLOUT_START_RE = re.compile(r"^>\s*\[!(?P<kind>[A-Za-z0-9_-]+)\]")
_CALLOUT_START_WITH_TITLE_RE = re.compile(r"^>\s*\[!(?P<kind>[A-Za-z0-9_-]+)\][+-]?\s*(?P<title>.*?)\s*$")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)(?:\n---\s*\n|\n\.\.\.\s*\n)", re.DOTALL)


def source_contains_codex_edition_markers(source: Path, prefix: str = "cx0") -> bool:
    """Return true if a source contains edition sentinels in ``prefix``'s namespace."""

    if not source.exists():
        return False
    text = source.read_text(encoding="utf-8", errors="ignore")
    return f"{prefix}:" in text and edition_marker_re(prefix).search(text) is not None


def source_contains_codex_editorial_callouts(source: Path) -> bool:
    """Return true if a source contains Obsidian-style editorial callouts."""

    if not source.exists():
        return False
    text = source.read_text(encoding="utf-8", errors="ignore")
    return any(_CALLOUT_START_RE.match(line) for line in text.splitlines())


def edition_from_source_frontmatter(source: Path) -> tuple[str, bool]:
    """Return (`codex_edition`, `codex_strip_editorial_callouts`) from YAML frontmatter.

    Supports top-level `codex_edition` / `codex_strip_editorial_callouts` and
    `variables.codex_edition` / `variables.codex_strip_editorial_callouts`.
    Returns empty edition when absent or unparsable.
    """

    if not source.exists():
        return "", False
    text = source.read_text(encoding="utf-8", errors="ignore")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return "", False
    try:
        import yaml
        data = yaml.safe_load(match.group("body")) or {}
    except Exception:
        return "", False
    if not isinstance(data, dict):
        return "", False
    variables = data.get("variables", {}) if isinstance(data.get("variables", {}), dict) else {}
    edition = data.get("codex_edition") or variables.get("codex_edition") or data.get("edition") or variables.get("edition")
    strip = data.get("codex_strip_editorial_callouts", variables.get("codex_strip_editorial_callouts",
                     data.get("strip_editorial_callouts", variables.get("strip_editorial_callouts", False))))
    return str(edition).strip() if edition else "", _truthy(strip)


def preprocess_codex_edition_blocks(
    source: Path,
    output_dir: Path,
    render_id: str,
    edition: str,
    *,
    strip_editorial_callouts: bool = False,
    format_editorial_callouts: bool = False,
    prefix: str = "cx0",
    labels: tuple[str, ...] | None = None,
) -> CodexEditionPreprocessResult:
    """``prefix``: the marker namespace (engine/markers.py). ``labels``: the editions the
    profile declares; when given, the selected edition and every marker label must be one.
    Errors name the profile's namespace."""
    try:
        return _preprocess(source, output_dir, render_id, edition, strip_editorial_callouts,
                           format_editorial_callouts, edition_marker_re(prefix), labels)
    except CodexEditionRenderError as exc:
        if prefix == "cx0":
            raise
        raise CodexEditionRenderError(str(exc).replace("cx0", prefix)) from None


def _preprocess(source, output_dir, render_id, edition, strip_editorial_callouts,
                format_editorial_callouts, rx, labels) -> CodexEditionPreprocessResult:
    """Select a Codex 0 edition from inline comment-sentinel variant blocks.

    The original source is never mutated. If no sentinels are present, returns
    `changed=False` and the original source path. If sentinels are present,
    `edition` is required and malformed/ambiguous variants fail hard rather than
    rendering all editions.
    """

    if not source.exists():
        return CodexEditionPreprocessResult(changed=False, rewritten_source=source)

    text = source.read_text(encoding="utf-8", errors="ignore")
    has_markers = rx.search(text) is not None
    if not has_markers:
        if strip_editorial_callouts:
            stripped_text, stripped_count = _strip_editorial_callouts(text)
            if stripped_count:
                output_dir.mkdir(parents=True, exist_ok=True)
                out_path = output_dir / f"{render_id}.codex_edition.md"
                out_path.write_text(stripped_text, encoding="utf-8")
                return CodexEditionPreprocessResult(
                    changed=True,
                    rewritten_source=out_path,
                    edition=edition,
                    editorial_callouts_stripped=stripped_count,
                )
        elif format_editorial_callouts:
            formatted_text, formatted_count = _format_editorial_callouts(text)
            if formatted_count:
                output_dir.mkdir(parents=True, exist_ok=True)
                out_path = output_dir / f"{render_id}.codex_edition.md"
                out_path.write_text(formatted_text, encoding="utf-8")
                return CodexEditionPreprocessResult(
                    changed=True,
                    rewritten_source=out_path,
                    edition=edition,
                    editorial_callouts_formatted=formatted_count,
                )
        return CodexEditionPreprocessResult(changed=False, rewritten_source=source, edition=edition)

    edition = str(edition or "").strip()
    if not edition:
        raise CodexEditionRenderError("Codex 0 edition variant markers found, but no codex_edition was selected")
    if not _safe_token(edition):
        raise CodexEditionRenderError(f"codex_edition is not a safe token: {edition!r}")
    if labels is not None and edition not in labels:
        raise CodexEditionRenderError(f"edition {edition!r} is not one this profile declares: {list(labels)}")

    rewritten, metadata = _select_variants(text, edition, rx)
    if labels is not None:
        unknown = sorted(set(metadata.get("labels_seen", ())) - set(labels))
        if unknown:
            raise CodexEditionRenderError(f"cx0:edition labels {unknown} are not editions this profile declares: {list(labels)}")
    if strip_editorial_callouts:
        rewritten, stripped_count = _strip_editorial_callouts(rewritten)
        formatted_count = 0
    elif format_editorial_callouts:
        rewritten, formatted_count = _format_editorial_callouts(rewritten)
        stripped_count = 0
    else:
        stripped_count = 0
        formatted_count = 0

    if rx.search(rewritten):
        raise CodexEditionRenderError("Codex edition preprocessing left cx0 sentinels in generated source")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{render_id}.codex_edition.md"
    out_path.write_text(rewritten, encoding="utf-8")
    return CodexEditionPreprocessResult(
        changed=True,
        rewritten_source=out_path,
        edition=edition,
        variant_count=metadata["variant_count"],
        selected_count=metadata["selected_count"],
        fallback_count=metadata["fallback_count"],
        editorial_callouts_stripped=stripped_count,
        editorial_callouts_formatted=formatted_count,
        selected_variant_ids=metadata["selected_variant_ids"],
        fallback_variant_ids=metadata["fallback_variant_ids"],
        warnings=metadata.get("warnings", []),
    )


def _marker_role(match: re.Match[str]) -> str:
    """Classify a cx0 marker as 'open', 'edition', or 'close'.

    Opens: `<!-- cx0:variant ... -->`. Closes: `<!-- cx0:endvariant -->` or the
    XML-style `<!-- /cx0:variant -->`. Editions: `<!-- cx0:edition ... -->`.
    """

    kind = match.group("kind").lower()
    if match.group("close"):
        return "close"
    if kind == "endvariant":
        return "close"
    if kind == "variant":
        return "open"
    return "edition"


def _select_variants(text: str, edition: str, rx: re.Pattern[str] = _MARKER_RE) -> tuple[str, dict[str, Any]]:
    out: list[str] = []
    pos = 0
    variant_count = 0
    selected_count = 0
    fallback_count = 0
    selected_variant_ids: list[str] = []
    fallback_variant_ids: list[str] = []
    warnings: list[str] = []
    labels_seen: set[str] = set()

    while True:
        match = rx.search(text, pos)
        if not match:
            out.append(text[pos:])
            break
        role = _marker_role(match)
        if role != "open":
            kind = match.group("kind").lower()
            raise CodexEditionRenderError(f"cx0:{kind} marker outside cx0:variant block")
        out.append(text[pos:match.start()])
        block, selected, used_fallback, block_warnings = _parse_variant_block(text, match, edition, rx)
        labels_seen.update(selected.get("labels", ()))
        out.append(block)
        variant_count += 1
        selected_count += 1
        variant_id = selected["variant_id"]
        selected_variant_ids.append(variant_id)
        if used_fallback:
            fallback_count += 1
            fallback_variant_ids.append(variant_id)
        warnings.extend(block_warnings)
        pos = selected["end_pos"]

    return "".join(out), {
        "variant_count": variant_count,
        "selected_count": selected_count,
        "fallback_count": fallback_count,
        "selected_variant_ids": selected_variant_ids,
        "fallback_variant_ids": fallback_variant_ids,
        "warnings": warnings,
        "labels_seen": sorted(labels_seen),
    }


def _parse_variant_block(
    text: str, start: re.Match[str], edition: str, rx: re.Pattern[str] = _MARKER_RE
) -> tuple[str, dict[str, Any], bool, list[str]]:
    attrs = _parse_attrs(start.group("attrs"))
    variant_id = attrs.get("id") or attrs.get("name") or f"variant@{start.start()}"
    if not _safe_token(variant_id):
        raise CodexEditionRenderError(f"cx0:variant has unsafe id: {variant_id!r}")

    warnings: list[str] = []
    if "fallback" in attrs:
        warnings.append(
            f"cx0:variant {variant_id}: the 'fallback' attribute is deprecated and ignored; "
            "the archival base (text before the first cx0:edition) is now the universal fallback"
        )

    # guard="witness,reader" restores fail-closed exposure for sensitive
    # regions: the listed editions MUST carry an explicit override and are not
    # allowed to inherit the raw archival base.
    guard = _guard_labels(attrs.get("guard", ""), variant_id)

    # Text between the open marker and the first cx0:edition marker is the
    # archival base — used for every edition unless a tagged override wins.
    base_start = start.end()
    base_body: str | None = None
    entries: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    current: dict[str, Any] | None = None
    cursor = start.end()

    while True:
        marker = rx.search(text, cursor)
        if marker is None:
            raise CodexEditionRenderError(
                f"cx0:variant {variant_id} is missing its close marker (cx0:endvariant or /cx0:variant)"
            )
        role = _marker_role(marker)
        if role == "open":
            raise CodexEditionRenderError(f"nested cx0:variant is not supported inside {variant_id}")
        if role == "edition":
            if current is None:
                base_body = text[base_start:marker.start()]
            else:
                current["body"] = text[current["body_start"]:marker.start()]
                entries.append(current)
            labels = _edition_labels(marker.group("attrs"), variant_id)
            register = _edition_register(marker.group("attrs"), variant_id)
            for label in labels:
                if label in seen_labels:
                    raise CodexEditionRenderError(f"duplicate cx0:edition {label!r} in variant {variant_id}")
                seen_labels.add(label)
            current = {"labels": set(labels), "register": register, "body_start": marker.end()}
            cursor = marker.end()
            continue
        # role == "close"
        if current is None:
            base_body = text[base_start:marker.start()]
        else:
            current["body"] = text[current["body_start"]:marker.start()]
            entries.append(current)
        break

    if base_body is None:
        base_body = ""

    selected_body: str | None = None
    selected_register = ""
    for entry in entries:
        if edition in entry["labels"]:
            selected_body = entry["body"]
            selected_register = entry.get("register", "")
            break
    used_fallback = False
    if selected_body is None:
        # No tagged override for this edition: inherit the archival base. When
        # overrides exist for other editions, treat this as a fallback for
        # metadata/telemetry so callers can see how many regions inherited raw.
        if edition in guard:
            raise CodexEditionRenderError(
                f"cx0:variant {variant_id} guards edition {edition!r}: it must have an explicit "
                "cx0:edition override and may not inherit the raw archival base"
            )
        selected_body = base_body
        used_fallback = bool(entries)

    return _wrap_register(_trim_selected_body(selected_body), selected_register), {
        "variant_id": variant_id,
        "end_pos": marker.end(),
        "labels": sorted({label for entry in entries for label in entry["labels"]} | set(guard)),
    }, used_fallback, warnings


def _trim_selected_body(body: str) -> str:
    # Keep prose readable in source while preventing marker-adjacent blank-line
    # accumulation in generated render sources. An empty selection (an addition
    # not present in this edition) collapses to nothing.
    if not body.strip():
        return ""
    return "\n" + body.strip("\n") + "\n"


def _parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw):
        attrs[match.group("key").lower()] = match.group("value").strip()
    return attrs


def _edition_labels(raw: str, variant_id: str) -> list[str]:
    attrs = _parse_attrs(raw)
    if "editions" in attrs:
        label_str = attrs["editions"]
    elif "edition" in attrs:
        label_str = attrs["edition"]
    else:
        # Bare-label form, optionally alongside non-label key="value" attributes
        # (e.g. register="pataphorical"). Strip the attr tokens; the remainder is
        # the comma-separated edition labels. A stray attr-only marker leaves an
        # empty label string and fails below, preserving the typo guard.
        label_str = _ATTR_RE.sub("", raw).strip()
    labels = [label.strip() for label in label_str.split(",") if label.strip()]
    if not labels:
        raise CodexEditionRenderError(f"cx0:edition in variant {variant_id} has no edition labels")
    for label in labels:
        if not _safe_token(label):
            raise CodexEditionRenderError(f"cx0:edition in variant {variant_id} has unsafe label: {label!r}")
    return labels


def _edition_register(raw: str, variant_id: str) -> str:
    """Return the optional `register="..."` label on a cx0:edition marker.

    A register is a rendering hint (e.g. `pataphorical`) that tags the selected
    prose with its narrative register so downstream lowering can add a running
    margin indicator. Absent register is the common case and adds no markup.
    """
    register = _parse_attrs(raw).get("register", "").strip()
    if register and not _safe_token(register):
        raise CodexEditionRenderError(
            f"cx0:edition in variant {variant_id} has unsafe register: {register!r}"
        )
    return register


def _wrap_register(body: str, register: str) -> str:
    """Wrap a selected block in a register-tagged fenced div when a register is set.

    The div carries a `codex-<register>` class (plus the raw `register` attribute)
    so the codex0 Pandoc filter can attach a margin rail marking the register.
    Empty selections (additions absent from this edition) stay empty.
    """
    if not register or not body.strip():
        return body
    return f"\n::: {{.codex-{register} register=\"{register}\"}}\n{body.strip(chr(10))}\n:::\n"


def _guard_labels(raw: str, variant_id: str) -> set[str]:
    labels = [label.strip() for label in raw.split(",") if label.strip()]
    for label in labels:
        if not _safe_token(label):
            raise CodexEditionRenderError(f"cx0:variant {variant_id} has unsafe guard label: {label!r}")
    return set(labels)


def _safe_token(value: str) -> bool:
    return bool(value and _SAFE_TOKEN_RE.match(value))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _strip_editorial_callouts(text: str) -> tuple[str, int]:
    """Strip Obsidian-style editorial callout blocks from generated source.

    This is intentionally broad for reader-facing Codex proofing: any blockquote
    beginning `> [!kind]` and its immediately following blockquote lines are
    removed. Ordinary non-callout blockquotes are preserved.

    Also normalizes surviving `---` thematic-break lines to `* * *`. Removing a
    callout can leave a bare `---` on a line adjacent to blank lines, and
    Pandoc's yaml_metadata_block extension will then parse that `---` as the
    start of a YAML metadata block and fail on the next line. `* * *` is an
    equivalent Markdown thematic break with no YAML ambiguity.
    """

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    stripped = 0
    i = 0
    while i < len(lines):
        if _CALLOUT_START_RE.match(lines[i]):
            stripped += 1
            i += 1
            while i < len(lines) and (lines[i].startswith(">") or lines[i].strip() == ""):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    result = "".join(out)
    result = _normalize_thematic_breaks(result)
    return result, stripped


def _normalize_thematic_breaks(text: str) -> str:
    """Rewrite standalone `---` thematic-break lines to `* * *`.

    Pandoc's yaml_metadata_block extension treats a line of exactly `---`
    (preceded by a blank line, terminated by `---` or `...`) as the start of a
    YAML metadata block. Body-level thematic breaks that use `---` therefore
    collide with the extension in assembled intermediates. `* * *` renders as
    the same thematic break in Pandoc output but is never a YAML sentinel.

    Preserves fenced code blocks (``` and ~~~ fenced regions) verbatim and
    skips a leading YAML frontmatter block if present so top-level manifest
    metadata is left alone.
    """
    out_lines: list[str] = []
    lines = text.splitlines()
    idx = 0
    total = len(lines)

    # Preserve a leading YAML frontmatter block (from the caller's own metadata
    # injection) — that opening `---` and its closing `---` are not thematic
    # breaks and must not be touched.
    if total > 0 and lines[0].strip() == "---":
        out_lines.append(lines[0])
        idx = 1
        while idx < total:
            out_lines.append(lines[idx])
            if lines[idx].strip() in ("---", "..."):
                idx += 1
                break
            idx += 1

    in_fence: str | None = None
    while idx < total:
        line = lines[idx]
        stripped_line = line.strip()
        if in_fence is None:
            if stripped_line.startswith("```"):
                in_fence = "```"
                out_lines.append(line)
                idx += 1
                continue
            if stripped_line.startswith("~~~"):
                in_fence = "~~~"
                out_lines.append(line)
                idx += 1
                continue
            if stripped_line == "---":
                out_lines.append("* * *")
                idx += 1
                continue
        else:
            if stripped_line.startswith(in_fence):
                in_fence = None
        out_lines.append(line)
        idx += 1
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")


def _format_editorial_callouts(text: str) -> tuple[str, int]:
    """Rewrite Obsidian-style callouts to Codex editorial-note fenced divs.

    This is source-level rather than a Lua-only transform because Pandoc folds
    adjacent blockquote lines into paragraphs, losing the title/body line break
    that Obsidian callouts rely on.
    """

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    formatted = 0
    i = 0
    while i < len(lines):
        start = _CALLOUT_START_WITH_TITLE_RE.match(lines[i])
        if not start:
            out.append(lines[i])
            i += 1
            continue

        formatted += 1
        kind = start.group("kind")
        title = start.group("title").strip()
        body: list[str] = []
        i += 1
        while i < len(lines) and (lines[i].startswith(">") or lines[i].strip() == ""):
            line = lines[i]
            if line.startswith(">"):
                body.append(re.sub(r"^> ?", "", line, count=1))
            else:
                body.append(line)
            i += 1

        out.append("\n" if out and out[-1].strip() else "")
        out.append(f'::: {{.codex-editorial-note kind="{_markdown_attr_escape(kind)}" title="{_markdown_attr_escape(title)}"}}\n')
        out.extend(body)
        if body and body[-1].strip():
            out.append("\n")
        out.append(":::\n\n")
    return "".join(out), formatted


def _markdown_attr_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r'\"')
