"""Single-object profile resolver for Optical Foundry.

This module is the single source of truth for resolving an individual
Markdown/object render profile into concrete Pandoc defaults, template, local
resource roots, TeX environment, profile family, and boundary evidence.

It deliberately does **not** decide how bundles, packet reviews, label sheets,
or other assembled artifacts are produced. That belongs to manifest resolution
and render planning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.font_resolver import POLICY_NAME, resolve_fonts_from_defaults

GF_ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMPORT = GF_ROOT / "profiles" / "40_latex_import"


ENGINE_LATEX_DIR = Path(__file__).resolve().parent / "latex"


@dataclass(frozen=True)
class RenderEnvironment:
    """Render-time path/environment facts for one resolved profile."""

    cwd: Path
    texmfhome: Path | None
    texinputs: str
    resource_paths: list[Path] = field(default_factory=list)
    # LuaTeX's require() path (LUAINPUTS does not follow TEXINPUTS on this TeX).
    luainputs: str = ""

    def env_overrides(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.texmfhome is not None:
            out["TEXMFHOME"] = str(self.texmfhome)
        if self.texinputs:
            out["TEXINPUTS"] = self.texinputs
        # LuaTeX's require() searches LUAINPUTS, which on this TeX does not
        # include TEXINPUTS: the engine's Lua modules (of_pages, of_plate_float)
        # must be on it explicitly. The trailing ':' keeps the default path.
        out["LUAINPUTS"] = self.luainputs or f"{ENGINE_LATEX_DIR}:"
        return out


@dataclass(frozen=True)
class ResolvedProfile:
    """Concrete profile resolution for one document/object render."""

    profile_id: str
    canonical_profile_id: str
    profile_family: str
    defaults_stack: list[Path]
    template_path: Path
    asset_roots: list[Path]
    render_environment: RenderEnvironment
    font_policy: dict[str, Any]
    boundary: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    # The source-preparation steps this profile uses (engine/source_preparation.py);
    # None means it declares none and gets every step (ruling 01a0f930-407c).
    source_preparation: tuple[str, ...] | None = None
    # A profile package (engine/profile_package.py, ruling 01a0f99a-b2db): its
    # directory, and the ornament slots it fills (engine/ornaments.py).
    package_dir: Path | None = None
    ornaments: dict[str, Any] | None = None
    # The chapter-opener contract it declares (engine/openers.py, map D4).
    openers: dict[str, Any] | None = None
    # Its marker namespace (engine/markers.py) and editions (engine/editions.py), map C1/C2.
    markers: dict[str, Any] | None = None
    editions: dict[str, Any] | None = None


ALIASES: dict[str, str] = {
    "tech": "yugen_tech",
    "risk": "yugen_risk",
    "creative": "yugen_creative",
    "civic": "yugen_civic",
    "yugen-civic": "yugen_civic",
    "generic_report": "generic-report",
    "mythic_letter": "mythic-letter",
    "mythic_letter_johannah": "mythic-letter-johannah",
    "mythic_letter_johannah_halfletter": "mythic-letter-johannah-halfletter",
    "codex0_a5": "codex0-a5",
    "codex_0": "codex0",
    "codex-0": "codex0",
    "prometheus_packet": "prometheus-packet",
    "household_paper": "household-paper",
    "household-newspaper": "household-paper",
    "short_story": "short-story",
}

# Explicit current mapping. Later this can be data-driven from profile YAML.
# A spec may name the source-preparation steps it uses with
# "source_preparation": [...] (step names in engine/source_preparation.STEPS);
# a spec that does not gets every step.
PROFILE_SPECS: dict[str, dict[str, Any]] = {
    "document-spine": {
        "family": "document_spine",
        "defaults": ["document_spine.yaml"],
        "template": "base.tex",
    },
    "generic-report": {
        "family": "document_spine",
        "defaults": ["generic_report.yaml"],
        "template": "generic_report.tex",
    },
    "yugen_tech": {
        "family": "document_spine",
        "defaults": ["document_spine.yaml", "yugenbase.yaml", "technology.yaml"],
        "template": "base.tex",
    },
    "yugen_risk": {
        "family": "document_spine",
        "defaults": ["document_spine.yaml", "yugenbase.yaml", "risk.yaml"],
        "template": "base.tex",
    },
    "yugen_creative": {
        "family": "document_spine",
        "defaults": ["document_spine.yaml", "yugenbase.yaml", "creative.yaml"],
        "template": "base.tex",
    },
    "yugen_civic": {
        "family": "document_spine",
        "defaults": ["document_spine.yaml", "yugenbase.yaml", "civic.yaml"],
        "template": "base.tex",
    },
    "cam": {"family": "document_spine", "defaults": ["document_spine.yaml", "yugenbase.yaml", "cam.yaml"], "template": "cam.tex"},
    "mythic": {"family": "document_spine", "defaults": ["document_spine.yaml", "yugenbase.yaml", "mythic.yaml"], "template": "mythic.tex"},
    # "codex0" left the engine on 2026-10-03 (map G2, ruling 01a100da-3cde): it is the
    # codex0 package in the profiles repository (optical-foundry-profiles/codex0).
    "codex0-a5": {
        "family": "document_spine",
        "defaults": ["document_spine.yaml", "yugenbase.yaml", "codex0_a5.yaml"],
        "template": "codex0_a5.tex",
    },
    "convergence": {"family": "document_spine", "defaults": ["document_spine.yaml", "yugenbase.yaml", "convergence.yaml"], "template": "convergence.tex"},
    "keeper": {"family": "document_spine", "defaults": ["document_spine.yaml", "yugenbase.yaml", "keeper.yaml"], "template": "keeper.tex"},
    "prometheus-packet": {"family": "document_spine", "defaults": ["prometheus_packet.yaml"], "template": "generic_report.tex"},
    "letter": {"family": "stationery_art", "defaults": ["letter.yaml"], "template": "personal_letter.tex"},
    "mythic-letter": {"family": "stationery_art", "defaults": ["mythic_letter.yaml"], "template": "personal_letter.tex"},
    "mythic-letter-johannah": {
        "family": "stationery_art",
        "defaults": ["yugenbase.yaml", "personal_letter.yaml", "mythic_letter_johannah.yaml"],
        "template": "mythic_letter_johannah.tex",
    },
    # Bound-object lane: same stationery identity at Codex 0's trim and measure.
    # Additive fork — the letterpaper parent above is load-bearing for Codex 0
    # Vol III witness plate 28 and must not be parameterized in place.
    "mythic-letter-johannah-halfletter": {
        "family": "stationery_art",
        "defaults": [
            "yugenbase.yaml",
            "personal_letter.yaml",
            "mythic_letter_johannah.yaml",
            "mythic_letter_johannah_halfletter.yaml",
        ],
        "template": "mythic_letter_johannah_halfletter.tex",
    },
    "resume": {"family": "resume", "defaults": ["resume_resume.yaml"], "template": "resume.tex"},
    "elian-packet": {"family": "campaign_art", "defaults": ["elian_packet.yaml"], "template": "elian_packet.tex"},
    "elian-poster": {"family": "campaign_art", "defaults": ["elian_poster.yaml"], "template": "elian_poster.tex"},
    "labels-avery-5164": {"family": "physical_sheet_profile", "defaults": ["labels_avery_5164.yaml"], "template": "label_sheet.tex"},
    "labels-avery-15264": {"family": "physical_sheet_profile", "defaults": ["labels_base.yaml"], "template": "label_sheet.tex"},
    "sticker-sheet": {"family": "physical_sheet_profile", "defaults": ["sticker_sheet.yaml"], "template": "label_sheet.tex"},
    "life": {
        "family": "document_spine",
        "defaults": ["document_spine.yaml", "yugenbase.yaml", "life.yaml"],
        "template": "base.tex",
    },
    "yugen-brand": {"family": "document_spine", "defaults": ["document_spine.yaml", "yugenbase.yaml"], "template": "generic_report.tex"},
    "yugen-brand-elevated": {"family": "document_spine", "defaults": ["document_spine.yaml", "yugenbase.yaml"], "template": "generic_report.tex"},
    # Household newspaper (descriptive handle; masthead unminted). Letter pages,
    # page-class grammar lowered by filters/household_paper.lua, greyscale only.
    "household-paper": {
        "family": "periodical",
        "defaults": ["household_paper.yaml"],
        "template": "household_paper.tex",
    },
    # One piece of short fiction at Codex 0's half-letter trim: Iowan, book
    # paragraphs, title block on page one, scene breaks and the opening drop cap
    # lowered by filters/short_story.lua. Opened 2026-09-29 for the horror
    # anthology seeds.
    "short-story": {
        "family": "document_spine",
        "defaults": ["short_story.yaml"],
        "template": "short_story.tex",
    },
}


def resolve_profile(profile_id: str) -> ResolvedProfile:
    """Resolve one profile ID/alias into concrete render facts."""

    canonical = ALIASES.get(profile_id, profile_id)
    spec = PROFILE_SPECS.get(canonical)
    package = None
    if spec is None:
        from engine.profile_package import find_package

        package = find_package(canonical)
    if package is not None:
        base_id = ALIASES.get(package.spec["extends"], package.spec["extends"])
        if base_id not in PROFILE_SPECS:
            raise ValueError(f"profile package {canonical}: extends {base_id!r}, which is not an engine profile")
        spec = dict(PROFILE_SPECS[base_id])
        for key in ("source_preparation", "markers", "editions", "family"):
            if package.spec.get(key) is not None:
                spec[key] = package.spec[key]
        # G2: a package that carries a whole profile names the engine defaults it
        # builds on, instead of taking the extended profile's stack.
        if package.spec.get("base_defaults") is not None:
            spec["defaults"] = list(package.spec["base_defaults"])
    if spec is None:
        spec = _fallback_spec(canonical)

    defaults_stack, defaults_sources = _resolve_defaults_stack(spec.get("defaults", []))
    template_path, template_source = _resolve_template(str(spec.get("template", "")))
    if package is not None:
        for name in package.spec.get("defaults") or []:
            path = (package.directory / name).resolve()
            if not path.is_file():
                raise ValueError(f"profile package {canonical}: defaults file missing: {path}")
            defaults_stack.append(path)
            defaults_sources.append("package")
        if package.spec.get("template"):
            template_path = (package.directory / package.spec["template"]).resolve()
            template_source = "package" if template_path.is_file() else "missing"

    local_texmf = LOCAL_IMPORT / "styles" / "texmf"
    texmfhome = local_texmf if local_texmf.exists() else None

    local_assets = LOCAL_IMPORT / "assets"
    asset_roots = [p for p in [local_assets] if p.exists()]
    # Profile defaults reference Foundry-owned assets as `assets/<name>`, so
    # resource roots include the local import root and its asset/template trees.
    resource_paths = [LOCAL_IMPORT, LOCAL_IMPORT / "templates", *asset_roots, GF_ROOT]
    texinputs_parts = [
        # Engine TeX and Lua (of_ornaments.tex, of_plates.tex, of_plate_float.lua ...):
        # on the search path for every render, so a profile's own files can require
        # the engine's (codex0_plate_float.lua is an alias of of_plate_float.lua).
        ENGINE_LATEX_DIR,
        LOCAL_IMPORT / "templates",
        LOCAL_IMPORT / "styles" / "texmf" / "tex" / "latex" / "generic",
        LOCAL_IMPORT / "styles" / "texmf" / "tex" / "latex" / "resume",
        LOCAL_IMPORT / "styles" / "texmf" / "tex" / "latex" / "yugen",
    ]
    # G2: a package's own TeX and Lua directories come first.
    package_tex = [(package.directory / d).resolve() for d in (package.spec.get("tex") or [])] if package else []
    for d in package_tex:
        if not d.is_dir():
            raise ValueError(f"profile package {canonical}: tex directory missing: {d}")
    texinputs_parts = [*package_tex, *texinputs_parts]
    texinputs = ":".join(str(p) for p in texinputs_parts if p.exists()) + ":"
    luainputs = ":".join(str(p) for p in [*package_tex, ENGINE_LATEX_DIR]) + ":"
    if package is not None:
        resource_paths = [package.directory, *resource_paths]

    source_preparation = spec.get("source_preparation")
    if source_preparation is not None:
        from engine.source_preparation import validate_declaration

        errors = validate_declaration(source_preparation)
        if errors:
            raise ValueError(f"profile {canonical}: {'; '.join(errors)}")
        source_preparation = tuple(source_preparation)

    uses_local = any(source == "local" for source in defaults_sources) or template_source == "local"
    font_policy = resolve_fonts_from_defaults(defaults_stack)
    warnings: list[str] = []
    if not defaults_stack:
        warnings.append(f"No defaults resolved for profile {profile_id}")
    if not template_path.exists():
        warnings.append(f"Template missing for profile {profile_id}: {template_path}")

    return ResolvedProfile(
        profile_id=profile_id,
        canonical_profile_id=canonical,
        profile_family=str(spec.get("family", "document_spine")),
        defaults_stack=defaults_stack,
        template_path=template_path,
        asset_roots=asset_roots,
        render_environment=RenderEnvironment(
            # Several inherited LaTeX templates use relative template variables
            # like assets/logo_yugen_navy_wordmark.png. Run Pandoc from the
            # local import root so those resolve against Foundry-owned assets.
            cwd=LOCAL_IMPORT if LOCAL_IMPORT.exists() else GF_ROOT,
            texmfhome=texmfhome,
            texinputs=texinputs,
            resource_paths=resource_paths,
            luainputs=luainputs,
        ),
        font_policy=font_policy,
        boundary={
            "target_legacy_profile_tree_mutated": False,
            "uses_local_imports": uses_local,
            "reads_legacy_profile_tree": False,
            "defaults_source": _summarize_sources(defaults_sources),
            "template_source": template_source,
            "profile_package": str(package.directory) if package is not None else None,
            "font_policy": POLICY_NAME,
        },
        warnings=warnings,
        source_preparation=source_preparation,
        package_dir=package.directory if package is not None else None,
        ornaments=(package.spec.get("ornaments") or None) if package is not None else None,
        openers=(package.spec.get("openers") or None) if package is not None else None,
        markers=_markers_of(spec, canonical),
        editions=_editions_of(spec, canonical),
    )


def _markers_of(spec: dict[str, Any], canonical: str) -> dict[str, Any] | None:
    markers = spec.get("markers")
    if markers is None:
        return None
    from engine.markers import MarkerError, validate_prefix

    try:
        return {"prefix": validate_prefix((markers or {}).get("prefix", "cx0"))}
    except MarkerError as exc:
        raise ValueError(f"profile {canonical}: {exc}") from None


def _editions_of(spec: dict[str, Any], canonical: str) -> dict[str, Any] | None:
    editions = spec.get("editions")
    if editions is None:
        return None
    if not isinstance(editions, dict):
        raise ValueError(f"profile {canonical}: editions must be a mapping, e.g. {{labels: [a, b]}}")
    labels = editions.get("labels")
    if labels is not None and (not isinstance(labels, list) or not all(isinstance(x, str) and x for x in labels)):
        raise ValueError(f"profile {canonical}: editions.labels must be a list of names")
    return {"labels": tuple(labels) if labels is not None else None}


def _fallback_spec(profile_id: str) -> dict[str, Any]:
    filename = profile_id.replace("-", "_")
    return {
        "family": "document_spine",
        "defaults": [f"{filename}.yaml"],
        "template": f"{filename}.tex",
    }


def _resolve_defaults_stack(names: list[str]) -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    sources: list[str] = []
    for name in names:
        local = LOCAL_IMPORT / "defaults" / name
        if local.exists():
            paths.append(local)
            sources.append("local")
        else:
            sources.append("missing")
    return paths, sources


def _resolve_template(name: str) -> tuple[Path, str]:
    local = LOCAL_IMPORT / "templates" / name
    if local.exists():
        return local, "local"
    return local, "missing"


def _summarize_sources(sources: list[str]) -> str:
    unique = set(sources)
    if not sources or unique == {"missing"}:
        return "missing"
    if unique == {"local"}:
        return "local"
    return "+".join(sorted(unique))
