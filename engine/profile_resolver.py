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


@dataclass(frozen=True)
class RenderEnvironment:
    """Render-time path/environment facts for one resolved profile."""

    cwd: Path
    texmfhome: Path | None
    texinputs: str
    resource_paths: list[Path] = field(default_factory=list)

    def env_overrides(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.texmfhome is not None:
            out["TEXMFHOME"] = str(self.texmfhome)
        if self.texinputs:
            out["TEXINPUTS"] = self.texinputs
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


ALIASES: dict[str, str] = {
    "tech": "yugen_tech",
    "risk": "yugen_risk",
    "creative": "yugen_creative",
    "civic": "yugen_civic",
    "yugen-civic": "yugen_civic",
    "generic_report": "generic-report",
    "mythic_letter": "mythic-letter",
    "mythic_letter_johannah": "mythic-letter-johannah",
    "codex0_a5": "codex0",
    "codex0-a5": "codex0",
    "codex_0": "codex0",
    "codex-0": "codex0",
    "prometheus_packet": "prometheus-packet",
}

# Explicit current mapping. Later this can be data-driven from profile YAML.
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
    "codex0": {"family": "document_spine", "defaults": ["document_spine.yaml", "yugenbase.yaml", "codex0.yaml"], "template": "codex0.tex"},
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
}


def resolve_profile(profile_id: str) -> ResolvedProfile:
    """Resolve one profile ID/alias into concrete render facts."""

    canonical = ALIASES.get(profile_id, profile_id)
    spec = PROFILE_SPECS.get(canonical)
    if spec is None:
        spec = _fallback_spec(canonical)

    defaults_stack, defaults_sources = _resolve_defaults_stack(spec.get("defaults", []))
    template_path, template_source = _resolve_template(str(spec.get("template", "")))

    local_texmf = LOCAL_IMPORT / "styles" / "texmf"
    texmfhome = local_texmf if local_texmf.exists() else None

    local_assets = LOCAL_IMPORT / "assets"
    asset_roots = [p for p in [local_assets] if p.exists()]
    # Profile defaults reference Foundry-owned assets as `assets/<name>`, so
    # resource roots include the local import root and its asset/template trees.
    resource_paths = [LOCAL_IMPORT, LOCAL_IMPORT / "templates", *asset_roots, GF_ROOT]
    texinputs_parts = [
        LOCAL_IMPORT / "templates",
        LOCAL_IMPORT / "styles" / "texmf" / "tex" / "latex" / "generic",
        LOCAL_IMPORT / "styles" / "texmf" / "tex" / "latex" / "resume",
        LOCAL_IMPORT / "styles" / "texmf" / "tex" / "latex" / "yugen",
    ]
    texinputs = ":".join(str(p) for p in texinputs_parts if p.exists()) + ":"

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
        ),
        font_policy=font_policy,
        boundary={
            "target_legacy_profile_tree_mutated": False,
            "uses_local_imports": uses_local,
            "reads_legacy_profile_tree": False,
            "defaults_source": _summarize_sources(defaults_sources),
            "template_source": template_source,
            "font_policy": POLICY_NAME,
        },
        warnings=warnings,
    )


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
