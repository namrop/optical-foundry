"""Page-size normalization and LaTeX geometry lowering.

This module keeps the source-facing page-size contract small and explicit while
letting the Pandoc/LaTeX renderer lower it through profile geometry variables.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


SUPPORTED_PAGE_SIZES = ("a4", "a5", "half_letter", "letter", "tabloid")

_PAGE_SIZE_ALIASES = {
    "letter": "letter",
    "letterpaper": "letter",
    "us_letter": "letter",
    "usletter": "letter",
    "a4": "a4",
    "a4paper": "a4",
    "a5": "a5",
    "a5paper": "a5",
    "half_letter": "half_letter",
    "halfletter": "half_letter",
    "statement": "half_letter",
    "statementpaper": "half_letter",
    "halfletterpaper": "half_letter",
    # 11 x 17 sheet: the household paper's folded spread (two letter pages per
    # side); auto-duplex ceiling on desk machines (WF-7840).
    "tabloid": "tabloid",
    "ledger": "tabloid",
    "11x17": "tabloid",
    "tabloidpaper": "tabloid",
}

_PAGE_SIZE_GEOMETRY = {
    "letter": ["letterpaper"],
    "a4": ["a4paper"],
    "a5": ["a5paper"],
    "half_letter": ["paperwidth=5.5in", "paperheight=8.5in"],
    "tabloid": ["paperwidth=11in", "paperheight=17in"],
}

_PAGE_SIZE_CLASSOPTION = {
    "letter": "letterpaper",
    "a4": "a4paper",
    "a5": "a5paper",
    "half_letter": "statementpaper",
}

_PAGE_GEOMETRY_PREFIXES = ("paperwidth=", "paperheight=", "paper=")
_PAGE_GEOMETRY_TOKENS = {
    "letterpaper",
    "a4paper",
    "a5paper",
    "b5paper",
    "legalpaper",
    "executivepaper",
    "statementpaper",
}


class PageSizeError(ValueError):
    """Raised when a requested page size is unsupported or malformed."""


class PageMarginError(ValueError):
    """Raised when a requested page margin is unsupported or malformed."""


_DIMENSION_RE = re.compile(r"^(?:\d+(?:\.\d+)?|\.\d+)(?:in|pt|mm|cm|pc|em|ex)$")
_MARGIN_KEYS = ("top", "bottom", "left", "right", "inner", "outer", "hmargin", "vmargin")


def normalize_page_size(value: Any, *, default: str = "letter", scope: str = "page_size") -> str:
    """Return a canonical page-size token.

    Supported canonical values are `letter`, `a4`, `a5`, and `half_letter`.
    Common paper/spacing aliases are accepted, but arbitrary dimensions are not;
    new physical sizes should be added deliberately because they affect layout,
    evidence, and profile behavior.
    """

    if value is None or value == "":
        return default
    if not isinstance(value, str):
        raise PageSizeError(f"{scope} must be one of: {', '.join(SUPPORTED_PAGE_SIZES)}")
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = _PAGE_SIZE_ALIASES.get(key)
    if normalized is None:
        raise PageSizeError(f"{scope} must be one of: {', '.join(SUPPORTED_PAGE_SIZES)}")
    return normalized


def page_size_from_mapping(values: dict[str, Any], *, scope: str) -> tuple[str, str]:
    """Resolve a page-size value from a mapping and return `(size, source)`.

    Recognizes `page_size`, `page-size`, and `papersize` as equivalent authored
    keys. If none are present, returns the default letter size and `default`.
    """

    for key in ("page_size", "page-size", "papersize"):
        if key in values and values.get(key) not in (None, ""):
            return normalize_page_size(values.get(key), scope=f"{scope}.{key}"), scope
    return "letter", "default"


def page_margins_from_mapping(values: dict[str, Any], *, scope: str) -> tuple[list[str], str]:
    """Resolve explicit page-margin overrides from a mapping.

    Supported authored forms are intentionally narrow and safe:
    `margin: 0.7in`, `page_margin: 0.7in`, `page-margin: 0.7in`, or
    `margins: {top: 0.7in, bottom: 0.8in, left: 0.65in, right: 0.65in}`.
    """

    for key in ("margin", "page_margin", "page-margin"):
        if key in values and values.get(key) not in (None, ""):
            margin = _normalize_margin_dimension(values.get(key), scope=f"{scope}.{key}")
            return [f"margin={margin}"], scope
    if "margins" in values and values.get("margins") not in (None, ""):
        margin_map = values.get("margins")
        if not isinstance(margin_map, dict):
            raise PageMarginError(f"{scope}.margins must be a mapping of margin names to plain TeX dimensions")
        unknown = sorted(str(key) for key in margin_map.keys() if key not in _MARGIN_KEYS)
        if unknown:
            raise PageMarginError(f"{scope}.margins supports only: {', '.join(_MARGIN_KEYS)}")
        options: list[str] = []
        for key in _MARGIN_KEYS:
            if key in margin_map and margin_map.get(key) not in (None, ""):
                options.append(f"{key}={_normalize_margin_dimension(margin_map.get(key), scope=f'{scope}.margins.{key}')}")
        return options, scope if options else "default"
    return [], "default"


def page_size_geometry_options(page_size: str) -> list[str]:
    """Return geometry-package options for a canonical page size."""

    canonical = normalize_page_size(page_size)
    return list(_PAGE_SIZE_GEOMETRY[canonical])


def profile_default_page_size(defaults_stack: list[Path]) -> tuple[str, str]:
    """Return a profile-authored page-size default from a defaults stack.

    Profile defaults are lower precedence than manifest/source page-size values
    but higher precedence than the renderer's historical letter default. The
    declaration may live at the defaults-file top level or inside ``variables``.
    """

    try:
        import yaml
    except Exception:
        return "letter", "default"

    resolved = "letter"
    found = False
    for defaults_file in defaults_stack:
        try:
            data = yaml.safe_load(defaults_file.read_text()) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for mapping in (data, data.get("variables", {})):
            if not isinstance(mapping, dict):
                continue
            page_size, source = page_size_from_mapping(mapping, scope=f"profile_defaults.{defaults_file.name}")
            if source != "default":
                resolved = page_size
                found = True
    return (resolved, "profile_defaults") if found else ("letter", "default")


def collect_profile_geometry(defaults_stack: list[Path]) -> list[str]:
    """Collect the effective profile geometry list from a defaults stack.

    Pandoc applies later defaults after earlier defaults. Profile imports keep
    geometry inside `variables.geometry`, so this reads each defaults file in
    order and keeps the latest geometry declaration.
    """

    geometry: list[str] = []
    try:
        import yaml
    except Exception:
        return geometry

    for defaults_file in defaults_stack:
        try:
            data = yaml.safe_load(defaults_file.read_text()) or {}
        except Exception:
            continue
        variables = data.get("variables", {}) if isinstance(data, dict) else {}
        if not isinstance(variables, dict) or "geometry" not in variables:
            continue
        value = variables.get("geometry")
        if isinstance(value, list):
            geometry = [str(item) for item in value if item is not None]
        elif isinstance(value, str):
            geometry = [value]
    return geometry


def collect_profile_classoption(defaults_stack: list[Path]) -> list[str]:
    """Collect the effective profile ``classoption`` list from defaults."""

    classoption: list[str] = []
    try:
        import yaml
    except Exception:
        return classoption

    for defaults_file in defaults_stack:
        try:
            data = yaml.safe_load(defaults_file.read_text()) or {}
        except Exception:
            continue
        variables = data.get("variables", {}) if isinstance(data, dict) else {}
        if not isinstance(variables, dict) or "classoption" not in variables:
            continue
        value = variables.get("classoption")
        if isinstance(value, list):
            classoption = [str(item) for item in value if item is not None]
        elif isinstance(value, str):
            classoption = [value]
    return classoption


def merge_page_size_geometry(
    page_size: str,
    existing_geometry: list[str],
    explicit_margins: list[str] | None = None,
) -> list[str]:
    """Merge page-size geometry ahead of profile/custom geometry options."""

    page_options = page_size_geometry_options(page_size)
    margin_options = list(explicit_margins or [])
    preserved = [
        option for option in existing_geometry
        if not _is_page_geometry_option(option) and not (margin_options and _is_margin_geometry_option(option))
    ]
    return [*page_options, *preserved, *margin_options]


def merge_page_size_classoption(page_size: str, existing_classoption: list[str]) -> list[str]:
    """Merge page-size document-class option into non-paper class options."""

    canonical = normalize_page_size(page_size)
    paper_option = _PAGE_SIZE_CLASSOPTION.get(canonical)
    preserved = [option for option in existing_classoption if not _is_classoption_paper_option(option)]
    return [*preserved, paper_option] if paper_option else preserved


def _is_page_geometry_option(option: str) -> bool:
    normalized = option.strip().lower().replace(" ", "")
    if normalized in _PAGE_GEOMETRY_TOKENS:
        return True
    return any(normalized.startswith(prefix) for prefix in _PAGE_GEOMETRY_PREFIXES)


def _is_classoption_paper_option(option: str) -> bool:
    normalized = option.strip().lower().replace(" ", "")
    return normalized in _PAGE_GEOMETRY_TOKENS


def _normalize_margin_dimension(value: Any, *, scope: str) -> str:
    if not isinstance(value, str):
        raise PageMarginError(f"{scope} must be a plain TeX dimension")
    normalized = value.strip().lower().replace(" ", "")
    if normalized.startswith("margin="):
        normalized = normalized.split("=", 1)[1]
    if not _DIMENSION_RE.match(normalized):
        raise PageMarginError(f"{scope} must be a plain TeX dimension")
    return normalized


def _is_margin_geometry_option(option: str) -> bool:
    normalized = option.strip().lower().replace(" ", "")
    if normalized.startswith("margin="):
        return True
    return any(normalized.startswith(f"{key}=") for key in _MARGIN_KEYS)
