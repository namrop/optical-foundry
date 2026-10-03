"""The marker grammar: HTML-comment control markers in Markdown sources (map C2).

A source carries invisible controls as comments in a namespace: ``<!-- cx0:breath -->``,
``<!-- cx0:variant id="x" -->``. Until 2026-10-03 the namespace ``cx0`` was spelled into
four parsers (editions, the bundle compiler's separator check, the source-preparation
gate, Codex 0's filter). A profile now declares its namespace (``markers: {prefix: cx0}``)
and every engine parser asks this module (ruling 01a100da-3cde).
"""
from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

DEFAULT_PREFIX = "cx0"   # the namespace sources used before profiles declared one
_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]{0,15}$")
# Any namespace's edition markers: how a profile without editions refuses them.
ANY_EDITION_MARKER_RE = re.compile(r"<!--\s*/?[a-z][a-z0-9]{0,15}:(?:variant|edition|endvariant)\b", re.IGNORECASE)


class MarkerError(ValueError):
    pass


def validate_prefix(prefix: Any) -> str:
    text = str(prefix or "")
    if not _PREFIX_RE.match(text):
        raise MarkerError(f"markers.prefix must be a short lowercase name like cx0, not {prefix!r}")
    return text


def prefix_of(markers: dict[str, Any] | None) -> str:
    """The profile's namespace, or the default when it declares none."""
    if not markers:
        return DEFAULT_PREFIX
    return validate_prefix(markers.get("prefix", DEFAULT_PREFIX))


@lru_cache(maxsize=None)
def edition_marker_re(prefix: str) -> re.Pattern[str]:
    p = re.escape(validate_prefix(prefix))
    return re.compile(rf"<!--\s*(?P<close>/)?{p}:(?P<kind>variant|edition|endvariant)\b(?P<attrs>.*?)-->",
                      re.IGNORECASE | re.DOTALL)


@lru_cache(maxsize=None)
def line_marker_re(prefix: str) -> re.Pattern[str]:
    """A whole line that is one marker; group 1 is the marker's name."""
    p = re.escape(validate_prefix(prefix))
    return re.compile(rf"^\s*<!--\s*{p}:([\w-]+).*?-->\s*$")


def marker(prefix: str, name: str) -> str:
    return f"<!-- {validate_prefix(prefix)}:{name} -->"
