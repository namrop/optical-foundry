"""Font policy resolver for Optical Foundry profiles.

The policy is deliberately small: Foundry-owned font files win when a defaults
stack points at local assets; named OS fonts are allowed only as explicit
compatibility fallbacks and are exposed in evidence instead of being silent
runtime assumptions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

GF_ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMPORT = GF_ROOT / "profiles" / "40_latex_import"
POLICY_NAME = "foundry_local_first_declared_system_fallback"

# These names are compatibility declarations inherited from the current profile
# defaults/templates. They are not vendored yet, so evidence should not pretend
# they are Foundry-owned assets.
DECLARED_SYSTEM_FALLBACKS = {
    "Helvetica",
    "Menlo",
    "Times New Roman",
    "Iowan Old Style",
    "Avenir Next",
    "Dune Rise",
    "Apple Color Emoji",
    "Noto Color Emoji",
    "DejaVu Sans",
}

FONT_ROLES = ("mainfont", "sansfont", "monofont")


def resolve_profile_fonts(resolved_profile: Any) -> dict[str, Any]:
    """Resolve font evidence from a ResolvedProfile-like object."""

    return resolve_fonts_from_defaults(list(getattr(resolved_profile, "defaults_stack", [])))


def resolve_fonts_from_defaults(defaults_stack: list[Path]) -> dict[str, Any]:
    """Return local-first font evidence for an ordered defaults stack."""

    merged: dict[str, tuple[Any, str]] = {}
    for defaults_path in defaults_stack:
        variables = _read_variables(defaults_path)
        source = f"defaults:{defaults_path.name}"
        for role in FONT_ROLES:
            file_key = f"{role}_file"
            dir_key = f"{role}_dir"
            if file_key in variables:
                merged[role] = (
                    {
                        "name": variables.get(role, ""),
                        "dir": variables.get(dir_key, ""),
                        "file": variables[file_key],
                    },
                    source,
                )
            elif role in variables:
                merged[role] = (variables[role], source)
        if "stationery_header_font_file" in variables:
            merged["stationery_header_font"] = (
                {
                    "dir": variables.get("stationery_header_font_dir", ""),
                    "file": variables["stationery_header_font_file"],
                },
                source,
            )

    fonts = [_resolve_font_role(role, value, source) for role, (value, source) in merged.items()]
    return {
        "policy": POLICY_NAME,
        "fonts": fonts,
        "summary": _summary(fonts),
    }


def _read_variables(path: Path) -> dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    variables = data.get("variables", {})
    return variables if isinstance(variables, dict) else {}


def _resolve_font_role(role: str, value: Any, source: str) -> dict[str, Any]:
    if isinstance(value, dict) and "file" in value:
        requested_name = str(value.get("name", "")) or None
        if role == "stationery_header_font":
            requested_name = None
        return _resolve_font_file(
            role,
            str(value.get("file", "")),
            str(value.get("dir", "")),
            source,
            requested_name=requested_name,
        )

    requested = str(value)
    local_file = _find_local_font_by_name(requested)
    if local_file is not None:
        return _entry(role, requested, "foundry_local", source, local_file)
    if requested in DECLARED_SYSTEM_FALLBACKS:
        return _entry(role, requested, "declared_system_fallback", source, None)
    return _entry(role, requested, "unresolved", source, None)


def _resolve_font_file(
    role: str,
    requested_file: str,
    requested_dir: str,
    source: str,
    requested_name: str | None = None,
) -> dict[str, Any]:
    candidates: list[Path] = []
    if requested_dir:
        base = Path(requested_dir)
        if base.is_absolute():
            candidates.append(base / requested_file)
        else:
            candidates.append(LOCAL_IMPORT / requested_dir / requested_file)
            candidates.append(LOCAL_IMPORT / "assets" / requested_dir / requested_file)
    candidates.append(LOCAL_IMPORT / "assets" / "fonts" / requested_file)

    for candidate in candidates:
        if candidate.exists():
            status = "foundry_local" if _is_relative_to(candidate, LOCAL_IMPORT) else "legacy_absolute_path"
            entry = _entry(role, requested_name or requested_file, status, source, candidate)
            if requested_name:
                entry["requested_file"] = requested_file
            return entry

    entry = _entry(role, requested_name or requested_file, "missing", source, None)
    if requested_name:
        entry["requested_file"] = requested_file
    return entry


def _find_local_font_by_name(requested: str) -> Path | None:
    requested_path = Path(requested)
    names = {requested}
    if requested_path.suffix:
        names.add(requested_path.name)
    for root in [LOCAL_IMPORT / "assets" / "fonts"]:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.name in names:
                return path
    return None


def _entry(role: str, requested: str, status: str, source: str, resolved_path: Path | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "role": role,
        "requested": requested,
        "status": status,
        "source": source,
    }
    if resolved_path is not None:
        entry["resolved_path"] = str(resolved_path)
    return entry


def _summary(fonts: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for font in fonts:
        status = str(font.get("status", "unknown"))
        out[status] = out.get(status, 0) + 1
    return out


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
