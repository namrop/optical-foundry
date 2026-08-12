"""Generic render-resource root normalization, ordering, and evidence.

The runtime has four resource ownership lanes, in fixed precedence order:
run-local generated assets, canonical source-local assets, manifest-declared
work assets, and profile-owned compatibility/style assets.  This module keeps
that ordering generic and records origin so render evidence can prove which
physical file supplied a logical reference.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Iterable

from engine.projection_plan import ProjectionPlan


@dataclass(frozen=True)
class ResolvedResourceRoot:
    """One canonical resource root in effective lookup order."""

    path: Path
    origin: str
    order: int

    def evidence(self) -> dict[str, Any]:
        return {"path": str(self.path), "origin": self.origin, "order": self.order}


def _tex_safe_root(path: Path) -> bool:
    text = path.as_posix().rstrip("/") + "/"
    if not text.startswith("/") or "://" in text:
        return False
    if any(ord(ch) < 32 for ch in text):
        return False
    return not any(
        ch in text
        for ch in ("\\", "{", "}", "$", "`", "%", "#", "&", "^", "~", os.pathsep)
    )


def resolve_manifest_resource_roots(
    manifest: dict[str, Any], *, manifest_path: Path | None = None
) -> list[Path]:
    """Validate and normalize optional top-level ``resource_roots``.

    Relative declarations are meaningful only with manifest provenance and are
    resolved from the manifest's directory, never from process CWD.  Canonical
    duplicate roots are removed while preserving the first declaration.
    """

    if "resource_roots" not in manifest:
        return []
    raw_roots = manifest.get("resource_roots")
    if not isinstance(raw_roots, list):
        raise ValueError("resource_roots must be a list of directory paths")
    if not raw_roots:
        raise ValueError("resource_roots must contain at least one directory path when present")

    normalized: list[Path] = []
    seen: set[Path] = set()
    for index, raw in enumerate(raw_roots):
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"resource_roots[{index}] must be a non-empty path string")
        value = raw.strip()
        if "://" in value:
            raise ValueError(f"resource_roots[{index}] must be a filesystem path, not a URL")
        declared = Path(value).expanduser()
        if declared.is_absolute():
            candidate = declared.resolve()
        else:
            if manifest_path is None:
                raise ValueError(
                    f"resource_roots[{index}] is relative but manifest_path provenance was not provided"
                )
            candidate = (Path(manifest_path).resolve().parent / declared).resolve()
        if not candidate.exists():
            raise ValueError(f"resource_roots[{index}] does not exist: {candidate}")
        if not candidate.is_dir():
            raise ValueError(f"resource_roots[{index}] is not a directory: {candidate}")
        if not _tex_safe_root(candidate):
            raise ValueError(f"resource_roots[{index}] resolves to a TeX-unsafe directory: {candidate}")
        if candidate not in seen:
            seen.add(candidate)
            normalized.append(candidate)
    return normalized


def _profile_resource_paths(profile: Any) -> list[Path]:
    environment = getattr(profile, "render_environment", None)
    raw = getattr(environment, "resource_paths", ()) if environment is not None else ()
    return [Path(path) for path in raw]


def effective_resource_roots(
    plan: ProjectionPlan,
    profile: Any,
    run_dir: Path,
) -> list[ResolvedResourceRoot]:
    """Return the canonical run → source → manifest → profile lookup chain."""

    source_roots = list(plan.source_resource_roots)
    if not source_roots:
        source_roots = [plan.render_source.resolve().parent]
    candidates: list[tuple[str, Path]] = [
        ("run", Path(run_dir)),
        *(("source", Path(path)) for path in source_roots),
        *(("manifest", Path(path)) for path in plan.manifest_resource_roots),
        *(("profile", path) for path in _profile_resource_paths(profile)),
    ]
    resolved: list[ResolvedResourceRoot] = []
    seen: set[Path] = set()
    for origin, path in candidates:
        canonical = path.expanduser().resolve()
        # Profile configuration may intentionally mention optional compatibility
        # roots, and the run root may be created later by the renderer. Source
        # roots and explicitly declared manifest roots must still exist at render
        # time so lookup ownership cannot disappear silently.
        if origin in {"source", "manifest"} and not canonical.is_dir():
            raise ValueError(
                f"{origin} resource root does not exist or is not a directory: {canonical}"
            )
        if origin == "profile" and not canonical.is_dir():
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        resolved.append(
            ResolvedResourceRoot(path=canonical, origin=origin, order=len(resolved))
        )
    return resolved


def resource_root_paths(roots: Iterable[ResolvedResourceRoot]) -> list[Path]:
    return [root.path for root in roots]


_TYPED_RESOURCE_KEYS = {
    "background_image",
    "image",
    "image_path",
    "logo_path",
    "print_image",
    "titlepage_background_image",
}
_RESOURCE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".pdf", ".png", ".svg", ".webp"}
_SUPPORTED_RAW_RESOURCE_MACROS = (
    r"(?:includegraphics|OFSectionDividerBackground|CodexFloatingPlate|OFOuterRail|OFBottomRail|OFEdgeOrnament)"
)
_RAW_RESOURCE_PREFIX = (
    rf"\\{_SUPPORTED_RAW_RESOURCE_MACROS}\b\s*(?:\[[^\]\r\n]*\]\s*)?"
)
_RAW_DETOKENIZED_RESOURCE_RE = re.compile(
    _RAW_RESOURCE_PREFIX
    + r"\{\s*\\detokenize\s*\{(?P<reference>[^{}\r\n]+)\}\s*\}"
)
_RAW_DIRECT_RESOURCE_RE = re.compile(
    _RAW_RESOURCE_PREFIX + r"\{\s*(?P<reference>[^{}\r\n]+?)\s*\}"
)
_TEMPLATE_RESOURCE_KEYS = ("titlepage_background_image", "logo_path")


def _relative_image_reference(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or "://" in value or "\x00" in value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in _RESOURCE_SUFFIXES:
        return None
    return path.as_posix()


def _collect_typed_references(value: Any, *, figure_context: bool = False) -> list[str]:
    references: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _TYPED_RESOURCE_KEYS or (figure_context and key == "path"):
                reference = _relative_image_reference(child)
                if reference:
                    references.append(reference)
            if isinstance(child, (dict, list)):
                references.extend(
                    _collect_typed_references(child, figure_context=figure_context)
                )
    elif isinstance(value, list):
        for child in value:
            references.extend(
                _collect_typed_references(child, figure_context=figure_context)
            )
    return references


def _raw_latex_resource_references(source: Path) -> list[str]:
    if not source.is_file():
        return []
    text = source.read_text(encoding="utf-8", errors="ignore")
    references: list[str] = []
    for pattern in (_RAW_DETOKENIZED_RESOURCE_RE, _RAW_DIRECT_RESOURCE_RE):
        for match in pattern.finditer(text):
            reference = _relative_image_reference(match.group("reference"))
            if reference:
                references.append(reference)
    return references


def _frontmatter_template_resource_references(source: Path) -> list[str]:
    """Return image paths consumed directly by supported Foundry templates."""

    if not source.is_file():
        return []
    text = source.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---", 4)
    if end == -1:
        return []
    try:
        import yaml

        frontmatter = yaml.safe_load(text[4:end]) or {}
    except Exception:
        return []
    if not isinstance(frontmatter, dict):
        return []
    nested = frontmatter.get("variables")
    mappings = [frontmatter, nested] if isinstance(nested, dict) else [frontmatter]
    references: list[str] = []
    for mapping in mappings:
        for key in _TEMPLATE_RESOURCE_KEYS:
            reference = _relative_image_reference(mapping.get(key))
            if reference:
                references.append(reference)
    return references


def typed_resource_references(plan: ProjectionPlan) -> list[str]:
    """Return distinct engine-visible and raw-LaTeX image references."""

    references = _collect_typed_references(plan.figure_inventory, figure_context=True)
    references.extend(_collect_typed_references(plan.boundary_assertions))
    references.extend(_frontmatter_template_resource_references(plan.render_source))
    references.extend(_raw_latex_resource_references(plan.render_source))
    unique: list[str] = []
    seen: set[str] = set()
    for reference in references:
        if reference not in seen:
            seen.add(reference)
            unique.append(reference)
    return unique


def resource_resolution_evidence(
    plan: ProjectionPlan,
    roots: list[ResolvedResourceRoot],
) -> dict[str, Any]:
    """Resolve typed resources and record winners, shadows, and warnings."""

    resolved_resources: list[dict[str, Any]] = []
    warnings: list[str] = []
    for reference in typed_resource_references(plan):
        matches: list[tuple[ResolvedResourceRoot, Path]] = []
        for root in roots:
            canonical_root = root.path.resolve()
            candidate = (canonical_root / reference).resolve()
            if candidate.is_relative_to(canonical_root) and candidate.is_file():
                matches.append((root, candidate))
        if not matches:
            resolved_resources.append(
                {
                    "reference": reference,
                    "winner": None,
                    "winner_origin": None,
                    "shadowed": [],
                }
            )
            warnings.append(f"resource reference did not resolve in the effective root chain: {reference}")
            continue
        winner_root, winner_path = matches[0]
        shadowed = [str(path) for _root, path in matches[1:]]
        resolved_resources.append(
            {
                "reference": reference,
                "winner": str(winner_path),
                "winner_origin": winner_root.origin,
                "shadowed": shadowed,
            }
        )
        if shadowed:
            noun = "match" if len(shadowed) == 1 else "matches"
            warnings.append(
                f"resource collision for {reference}: {winner_root.origin} winner shadows "
                f"{len(shadowed)} lower-precedence {noun}"
            )
    return {
        "effective_roots": [root.evidence() for root in roots],
        "resolved_resources": resolved_resources,
        "warnings": warnings,
    }
