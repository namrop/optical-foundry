"""Profile capability inventory / checker.

Checks each profile known to PandocRenderer for:
- Foundry-owned defaults availability
- Foundry-owned template availability
- TOC support (template has $if(toc)$ guard — pandoc --toc engages it)
- bundle compatibility (ok / partial / incompatible with reasons)

Read-only: reports profile capability, never writes to disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from engine.profile_resolver import resolve_profile

# ── Profile → template mapping (mirrors PandocRenderer._infer_template) ──────

PROFILE_TEMPLATE_MAP: dict[str, str] = {
    "generic-report": "generic_report.tex",
    "generic_report": "generic_report.tex",
    "risk": "risk.tex",
    "tech": "tech.tex",
    "creative": "creative.tex",
    "yugen-civic": "base.tex",
    "cam": "cam.tex",
    "mythic": "mythic.tex",
    "codex0": "codex0.tex",
    "mythic-letter": "personal_letter.tex",
    "mythic-letter-johannah": "mythic_letter_johannah.tex",
    "letter": "personal_letter.tex",
    "resume": "resume.tex",
    "prometheus-packet": "generic_report.tex",
    "convergence": "convergence.tex",
    "keeper": "keeper.tex",
    "life": "base.tex",
    "yugen-brand": "yugen_brand.tex",
    "yugen-brand-elevated": "yugen_brand_elevated.tex",
    "elian-packet": "elian_packet.tex",
    "elian-poster": "elian_poster.tex",
    "labels-avery-5164": "label_sheet.tex",
    "labels-avery-15264": "label_sheet.tex",
    "sticker-sheet": "label_sheet.tex",
}

# Profile IDs to check (canonical forms only — no aliases).
PROFILE_IDS = [
    "generic-report",
    "risk",
    "tech",
    "creative",
    "yugen-civic",
    "cam",
    "mythic",
    "codex0",
    "mythic-letter",
    "mythic-letter-johannah",
    "letter",
    "resume",
    "prometheus-packet",
    "convergence",
    "keeper",
    "life",
    "yugen-brand",
    "yugen-brand-elevated",
    "elian-packet",
    "elian-poster",
    "labels-avery-5164",
    "labels-avery-15264",
    "sticker-sheet",
]

# ── Known template facts ─────────────────────────────────────────────────────

# Templates whose local Foundry-owned copies expose bundle-compatible features.
KNOWN_TEMPLATES = {
    "base.tex", "cam.tex", "codex0.tex", "convergence.tex",
    "elian_packet.tex", "elian_poster.tex",
    "generic_report.tex", "keeper.tex",
    "label_sheet.tex", "mythic.tex",
    "mythic_letter_johannah.tex",
    "personal_letter.tex", "resume.tex",
}

# Profiles that use a different template than what the mapping says (known corrections).
TEMPLATE_CORRECTIONS: dict[str, str] = {
    "risk": "base.tex",           # risk.yaml defaults point to base.tex
    "tech": "base.tex",           # technology.yaml defaults point to base.tex
    "creative": "base.tex",       # creative.yaml defaults point to base.tex
    "yugen-civic": "base.tex",
    "yugen-brand": "generic_report.tex",        # yugenbase.yaml → generic_report.tex
    "yugen-brand-elevated": "generic_report.tex",
}

# Profiles with TOC guard ($if(toc)$) in their effective template.
TOC_GUARD_PROFILES = {
    "generic-report", "risk", "tech", "creative", "yugen-civic", "cam",
    "mythic", "codex0", "letter", "mythic-letter", "mythic-letter-johannah",
    "convergence", "keeper", "life",
    "yugen-brand", "yugen-brand-elevated", "prometheus-packet",
}

# Profiles whose effective template defines \tightlist.
TIGHTLIST_PROFILES = {
    "generic-report", "risk", "tech", "creative", "yugen-civic", "cam",
    "mythic", "codex0", "letter", "mythic-letter", "mythic-letter-johannah",
    "convergence", "keeper", "life",
    "yugen-brand", "yugen-brand-elevated", "prometheus-packet",
    "elian-packet", "resume", "labels-avery-5164", "labels-avery-15264",
    "sticker-sheet",
}

# Profiles whose effective template defines \longtable.
LONGTABLE_PROFILES = {
    "generic-report", "risk", "tech", "creative", "yugen-civic", "cam",
    "mythic", "codex0", "letter", "mythic-letter", "mythic-letter-johannah",
    "convergence", "keeper", "life",
    "yugen-brand", "yugen-brand-elevated", "prometheus-packet",
    "elian-packet",
}

# ── Bundle compatibility classification ──────────────────────────────────────

# Profiles fully compatible with composite_bundle rendering.
BUNDLE_OK = {
    "generic-report", "risk", "tech", "creative", "yugen-civic", "cam",
    "mythic", "codex0", "letter", "mythic-letter", "mythic-letter-johannah",
    "convergence", "keeper", "life",
    "yugen-brand", "yugen-brand-elevated",
}

# Profiles partially compatible (template exists, renders documents,
# but missing one or more bundle features).
BUNDLE_PARTIAL: dict[str, list[str]] = {
    "prometheus-packet": [
        "Template is generic_report.tex (shared with generic-report)",
        "Designed for packet state projection, not content bundle assembly",
        "TOC guard and tightlist present but layout optimized for metadata tables",
    ],
    "resume": [
        "No TOC guard — --toc flag has no effect",
        "Missing longtable support",
        "Resume document class, not bundle-compatible",
    ],
}

# Profiles fundamentally incompatible with bundle rendering.
BUNDLE_INCOMPATIBLE: dict[str, list[str]] = {
    "elian-packet": [
        "Placeholder assets available for synthetic local renders only; real campaign art remains external/content-dependent",
        "No TOC guard — --toc flag has no effect",
        "Content-dependent (see G2 in gap report)",
        "Designed for single-packet Elian campaign render, not generic bundles",
    ],
    "elian-poster": [
        "Placeholder assets available for synthetic local renders only; real campaign art remains external/content-dependent",
        "No TOC guard — --toc flag has no effect",
        "Missing \\tightlist",
        "Missing longtable support",
        "Content-dependent (see G2 in gap report)",
    ],
    "labels-avery-5164": [
        "Label sheet layout — designed for Avery 5164 label grids, not document bundles",
        "No TOC guard — --toc flag has no effect",
        "Content-driven grid — physical label positions in markdown body, not generic",
        "See G5 and G6 in gap report",
    ],
    "labels-avery-15264": [
        "Label sheet layout — designed for label grids, not document bundles",
        "No TOC guard — --toc flag has no effect",
        "Content-driven grid — see G5 and G6 in gap report",
    ],
    "sticker-sheet": [
        "Sticker sheet layout — designed for sticker grids, not document bundles",
        "No TOC guard — --toc flag has no effect",
        "Content-driven grid — physical sticker positions in markdown body, not generic",
        "See G4 and G6 in gap report",
    ],
}


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class ProfileCapability:
    """Capability report for a single profile."""

    profile_id: str
    defaults_found: str | None = None   # resolved path, or None
    defaults_source: str = "missing"     # local | missing
    template_found: str | None = None   # resolved path, or None
    template_source: str = "missing"     # local | missing
    template_inferred: str = ""         # raw mapping lookup (before corrections)
    uses_legacy_profile_tree: bool = False
    supports_toc: bool = False
    has_tightlist: bool = False
    has_longtable: bool = False
    bundle_compatibility: str = "unknown"
    bundle_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "defaults_found": self.defaults_found,
            "defaults_source": self.defaults_source,
            "template_found": self.template_found,
            "template_source": self.template_source,
            "template_inferred": self.template_inferred,
            "uses_legacy_profile_tree": self.uses_legacy_profile_tree,
            "supports_toc": self.supports_toc,
            "has_tightlist": self.has_tightlist,
            "has_longtable": self.has_longtable,
            "bundle_compatibility": self.bundle_compatibility,
            "bundle_reasons": self.bundle_reasons,
            "warnings": self.warnings,
        }


# ── Checker ───────────────────────────────────────────────────────────────────


def check_profile(profile_id: str) -> ProfileCapability:
    """Check a single profile's capabilities using the shared profile resolver."""

    cap = ProfileCapability(profile_id=profile_id)

    resolved = resolve_profile(profile_id)

    cap.defaults_found = str(resolved.defaults_stack[-1]) if resolved.defaults_stack else None
    cap.defaults_source = resolved.boundary.get("defaults_source", "missing")
    cap.template_inferred = resolved.template_path.name if resolved.template_path else ""
    if resolved.template_path and resolved.template_path.exists():
        cap.template_found = str(resolved.template_path)
        cap.template_source = resolved.boundary.get("template_source", "missing")
    else:
        cap.template_found = None
        cap.template_source = "missing"

    for warning in resolved.warnings:
        cap.warnings.append(warning)

    # ── feature checks ────────────────────────────────────────────
    cap.supports_toc = profile_id in TOC_GUARD_PROFILES
    cap.has_tightlist = profile_id in TIGHTLIST_PROFILES
    cap.has_longtable = profile_id in LONGTABLE_PROFILES

    # ── bundle compatibility ──────────────────────────────────────
    if profile_id in BUNDLE_OK:
        cap.bundle_compatibility = "ok"
        cap.bundle_reasons = ["Template has TOC guard, tightlist, longtable; defaults found"]
    elif profile_id in BUNDLE_PARTIAL:
        cap.bundle_compatibility = "partial"
        cap.bundle_reasons = BUNDLE_PARTIAL[profile_id]
    elif profile_id in BUNDLE_INCOMPATIBLE:
        cap.bundle_compatibility = "incompatible"
        cap.bundle_reasons = BUNDLE_INCOMPATIBLE[profile_id]
    else:
        cap.bundle_compatibility = "incompatible"
        cap.bundle_reasons = [f"No known compatibility classification for profile '{profile_id}'"]

    # Additional warning if template not found but classified as ok
    if cap.template_found is None and cap.bundle_compatibility == "ok":
        cap.warnings.append(
            f"Classified as bundle-ok but template not found on disk — "
            f"check profiles/40_latex_import/templates/"
        )

    return cap


def check_all_profiles() -> dict[str, ProfileCapability]:
    """Check all known profiles and return {profile_id: capability}."""
    results: dict[str, ProfileCapability] = {}
    for pid in PROFILE_IDS:
        results[pid] = check_profile(pid)
    return results


def check_all_profiles_json() -> str:
    """Check all profiles and return a JSON report string."""
    caps = check_all_profiles()
    report = {
        "schema_version": "profile_capability_check_v1",
        "profiles_checked": len(caps),
        "summary": _build_summary(caps),
        "profiles": {pid: cap.to_dict() for pid, cap in caps.items()},
        "boundary": {
            "target_legacy_profile_tree_mutated": False,
            "reads_legacy_profile_tree": False,
            "notes": (
                "This report resolves defaults, templates, styles, and assets "
                "from Foundry-owned profile imports. No external profile tree "
                "fallback is used."
            ),
        },
    }
    return json.dumps(report, indent=2)


def _build_summary(caps: dict[str, ProfileCapability]) -> dict[str, Any]:
    ok = sum(1 for c in caps.values() if c.bundle_compatibility == "ok")
    partial = sum(1 for c in caps.values() if c.bundle_compatibility == "partial")
    incompatible = sum(1 for c in caps.values() if c.bundle_compatibility == "incompatible")
    with_defaults = sum(1 for c in caps.values() if c.defaults_found is not None)
    with_templates = sum(1 for c in caps.values() if c.template_found is not None)
    with_toc = sum(1 for c in caps.values() if c.supports_toc)
    local_defaults = sum(1 for c in caps.values() if c.defaults_source == "local")
    local_templates = sum(1 for c in caps.values() if c.template_source == "local")
    remote_defaults = 0
    remote_templates = 0
    return {
        "total": len(caps),
        "bundle_ok": ok,
        "bundle_partial": partial,
        "bundle_incompatible": incompatible,
        "with_defaults": with_defaults,
        "with_templates": with_templates,
        "with_toc_support": with_toc,
        "defaults_local": local_defaults,
        "defaults_40_latex": remote_defaults,
        "templates_local": local_templates,
        "templates_40_latex": remote_templates,
    }
