"""Preprocess Codex 0 inline edition variants before Pandoc.

Codex 0 keeps edition-specific prose side-by-side in the Markdown source using
HTML comment sentinels so the manuscript remains readable/editable as prose:

    <!-- cx0:variant id="how-you-arrived-010" fallback="johannah" -->
    <!-- cx0:edition johannah -->
    Literal/private prose.
    <!-- cx0:edition reader -->
    Wider-reader prose.
    <!-- cx0:endvariant -->

This preprocessor selects one edition before the existing Optical Foundry source
preprocessors run. That ordering keeps inactive `of-image`, Mermaid, Vega, D2,
and Graphviz blocks out of downstream preprocessors.
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
    selected_variant_ids: list[str] = field(default_factory=list)
    fallback_variant_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_MARKER_RE = re.compile(r"<!--\s*cx0:(?P<kind>variant|edition|endvariant)\b(?P<attrs>.*?)-->", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)=(?P<quote>[\"'])(?P<value>.*?)(?P=quote)")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_CALLOUT_START_RE = re.compile(r"^>\s*\[!(?P<kind>[A-Za-z0-9_-]+)\]")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)(?:\n---\s*\n|\n\.\.\.\s*\n)", re.DOTALL)


def source_contains_codex_edition_markers(source: Path) -> bool:
    """Return true if a source contains Codex 0 edition sentinels."""

    if not source.exists():
        return False
    text = source.read_text(encoding="utf-8", errors="ignore")
    return "cx0:" in text and _MARKER_RE.search(text) is not None


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
    strip = data.get("codex_strip_editorial_callouts", variables.get("codex_strip_editorial_callouts", False))
    return str(edition).strip() if edition else "", _truthy(strip)


def preprocess_codex_edition_blocks(
    source: Path,
    output_dir: Path,
    render_id: str,
    edition: str,
    *,
    strip_editorial_callouts: bool = False,
) -> CodexEditionPreprocessResult:
    """Select a Codex 0 edition from inline comment-sentinel variant blocks.

    The original source is never mutated. If no sentinels are present, returns
    `changed=False` and the original source path. If sentinels are present,
    `edition` is required and malformed/ambiguous variants fail hard rather than
    rendering all editions.
    """

    if not source.exists():
        return CodexEditionPreprocessResult(changed=False, rewritten_source=source)

    text = source.read_text(encoding="utf-8", errors="ignore")
    has_markers = "cx0:" in text and _MARKER_RE.search(text) is not None
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
        return CodexEditionPreprocessResult(changed=False, rewritten_source=source, edition=edition)

    edition = str(edition or "").strip()
    if not edition:
        raise CodexEditionRenderError("Codex 0 edition variant markers found, but no codex_edition was selected")
    if not _safe_token(edition):
        raise CodexEditionRenderError(f"codex_edition is not a safe token: {edition!r}")

    rewritten, metadata = _select_variants(text, edition)
    if strip_editorial_callouts:
        rewritten, stripped_count = _strip_editorial_callouts(rewritten)
    else:
        stripped_count = 0

    if _MARKER_RE.search(rewritten):
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
        selected_variant_ids=metadata["selected_variant_ids"],
        fallback_variant_ids=metadata["fallback_variant_ids"],
    )


def _select_variants(text: str, edition: str) -> tuple[str, dict[str, Any]]:
    out: list[str] = []
    pos = 0
    variant_count = 0
    selected_count = 0
    fallback_count = 0
    selected_variant_ids: list[str] = []
    fallback_variant_ids: list[str] = []

    while True:
        match = _MARKER_RE.search(text, pos)
        if not match:
            out.append(text[pos:])
            break
        kind = match.group("kind").lower()
        if kind != "variant":
            raise CodexEditionRenderError(f"cx0:{kind} marker outside cx0:variant block")
        out.append(text[pos:match.start()])
        block, selected, used_fallback = _parse_variant_block(text, match, edition)
        out.append(block)
        variant_count += 1
        selected_count += 1
        variant_id = selected["variant_id"]
        selected_variant_ids.append(variant_id)
        if used_fallback:
            fallback_count += 1
            fallback_variant_ids.append(variant_id)
        pos = selected["end_pos"]

    return "".join(out), {
        "variant_count": variant_count,
        "selected_count": selected_count,
        "fallback_count": fallback_count,
        "selected_variant_ids": selected_variant_ids,
        "fallback_variant_ids": fallback_variant_ids,
    }


def _parse_variant_block(text: str, start: re.Match[str], edition: str) -> tuple[str, dict[str, Any], bool]:
    attrs = _parse_attrs(start.group("attrs"))
    variant_id = attrs.get("id") or attrs.get("name") or f"variant@{start.start()}"
    fallback = attrs.get("fallback", "")
    if not _safe_token(variant_id):
        raise CodexEditionRenderError(f"cx0:variant has unsafe id: {variant_id!r}")
    if fallback and not _safe_token(fallback):
        raise CodexEditionRenderError(f"cx0:variant {variant_id} has unsafe fallback: {fallback!r}")

    entries: list[dict[str, Any]] = []
    cursor = start.end()
    current: dict[str, Any] | None = None

    while True:
        marker = _MARKER_RE.search(text, cursor)
        if marker is None:
            raise CodexEditionRenderError(f"cx0:variant {variant_id} is missing cx0:endvariant")
        kind = marker.group("kind").lower()
        if kind == "variant":
            raise CodexEditionRenderError(f"nested cx0:variant is not supported inside {variant_id}")
        if kind == "edition":
            if current is not None:
                current["body"] = text[current["body_start"]:marker.start()]
                entries.append(current)
            label = _edition_label(marker.group("attrs"), variant_id)
            if any(entry["edition"] == label for entry in entries):
                raise CodexEditionRenderError(f"duplicate cx0:edition {label!r} in variant {variant_id}")
            current = {"edition": label, "body_start": marker.end()}
            cursor = marker.end()
            continue
        if kind == "endvariant":
            if current is not None:
                current["body"] = text[current["body_start"]:marker.start()]
                entries.append(current)
            if not entries:
                raise CodexEditionRenderError(f"cx0:variant {variant_id} has no cx0:edition branches")
            labels = [entry["edition"] for entry in entries]
            selected_label = edition if edition in labels else fallback
            used_fallback = False
            if selected_label and selected_label not in labels:
                raise CodexEditionRenderError(
                    f"cx0:variant {variant_id} has no branch for edition {edition!r} and fallback {fallback!r} is missing"
                )
            if not selected_label:
                raise CodexEditionRenderError(
                    f"cx0:variant {variant_id} has no branch for edition {edition!r} and no fallback"
                )
            if selected_label != edition:
                used_fallback = True
            body = next(entry["body"] for entry in entries if entry["edition"] == selected_label)
            return _trim_selected_body(body), {
                "variant_id": variant_id,
                "edition": selected_label,
                "end_pos": marker.end(),
            }, used_fallback


def _trim_selected_body(body: str) -> str:
    # Keep prose readable in source while preventing marker-adjacent blank-line
    # accumulation in generated render sources.
    return "\n" + body.strip("\n") + "\n"


def _parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw):
        attrs[match.group("key").lower()] = match.group("value").strip()
    return attrs


def _edition_label(raw: str, variant_id: str) -> str:
    attrs = _parse_attrs(raw)
    if "edition" in attrs:
        label = attrs["edition"]
    elif attrs:
        # Unknown attributes without an explicit edition are probably a typo.
        raise CodexEditionRenderError(f"cx0:edition in variant {variant_id} must specify edition=... or a bare label")
    else:
        label = raw.strip()
    if not _safe_token(label):
        raise CodexEditionRenderError(f"cx0:edition in variant {variant_id} has unsafe label: {label!r}")
    return label


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
    return "".join(out), stripped
