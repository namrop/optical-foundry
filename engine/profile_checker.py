"""Profile capability inventory / checker.

Checks each profile known to PandocRenderer for:
- defaults availability (40_latex defaults/ or greenfield profiles/)
- template availability (40_latex templates/)
- TOC support (template has $if(toc)$ guard — pandoc --toc engages it)
- bundle compatibility (ok / partial / incompatible with reasons)

Read-only: never mutates 40_latex, never writes to disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Read-only reference path for 40_latex.
LATEX40 = Path("~/Digital_Workspace/40_latex")

# ── Profile → template mapping (mirrors PandocRenderer._infer_template) ──────

PROFILE_TEMPLATE_MAP: dict[str, str] = {
    "generic-report": "generic_report.tex",
    "generic_report": "generic_report.tex",
    "risk": "risk.tex",
    "tech": "tech.tex",
    "creative": "creative.tex",
    "cam": "cam.tex",
    "mythic": "mythic.tex",
    "mythic-letter": "mythic_letter.tex",
    "mythic-letter-johannah": "mythic_letter_johannah.tex",
    "letter": "letter.tex",
    "resume": "resume.tex",
    "prometheus-packet": "prometheus_packet.tex",
    "convergence": "convergence.tex",
    "keeper": "keeper.tex",
    "yugen-brand": "yugen_brand.tex",
    "yugen-brand-elevated": "yugen_brand_elevated.tex",
    "elian-packet": "elian_packet.tex",
    "elian-poster": "elian_poster.tex",
    "labels-avery-5164": "labels_avery_5164.tex",
    "labels-avery-15264": "labels_avery_5164.tex",
    "sticker-sheet": "sticker_sheet.tex",
}

# Profile IDs to check (canonical forms only — no aliases).
PROFILE_IDS = [
    "generic-report",
    "risk",
    "tech",
    "creative",
    "cam",
    "mythic",
    "mythic-letter",
    "mythic-letter-johannah",
    "letter",
    "resume",
    "prometheus-packet",
    "convergence",
    "keeper",
    "yugen-brand",
    "yugen-brand-elevated",
    "elian-packet",
    "elian-poster",
    "labels-avery-5164",
    "labels-avery-15264",
    "sticker-sheet",
]

# ── Known template facts ─────────────────────────────────────────────────────

# Templates that exist on disk in 40_latex/templates/
KNOWN_TEMPLATES = {
    "base.tex", "cam.tex", "convergence.tex",
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
    "letter": "personal_letter.tex",       # actual file is personal_letter.tex
    "mythic-letter": "personal_letter.tex",  # shares personal_letter.tex
    "prometheus-packet": "generic_report.tex",  # prometheus_packet.yaml → generic_report.tex
    "labels-avery-5164": "label_sheet.tex",     # actual file is label_sheet.tex
    "labels-avery-15264": "label_sheet.tex",    # same template
    "sticker-sheet": "label_sheet.tex",         # sticker_sheet.yaml → label_sheet.tex
    "yugen-brand": "generic_report.tex",        # yugenbase.yaml → generic_report.tex
    "yugen-brand-elevated": "generic_report.tex",
}

# Profiles with TOC guard ($if(toc)$) in their effective template.
TOC_GUARD_PROFILES = {
    "generic-report", "risk", "tech", "creative", "cam",
    "mythic", "convergence", "keeper",
    "yugen-brand", "yugen-brand-elevated", "prometheus-packet",
}

# Profiles whose effective template defines \tightlist.
TIGHTLIST_PROFILES = {
    "generic-report", "risk", "tech", "creative", "cam",
    "mythic", "convergence", "keeper",
    "yugen-brand", "yugen-brand-elevated", "prometheus-packet",
    "elian-packet", "resume", "labels-avery-5164", "labels-avery-15264",
    "sticker-sheet",
}

# Profiles whose effective template defines \longtable.
LONGTABLE_PROFILES = {
    "generic-report", "risk", "tech", "creative", "cam",
    "mythic", "convergence", "keeper",
    "yugen-brand", "yugen-brand-elevated", "prometheus-packet",
    "elian-packet",
}

# ── Bundle compatibility classification ──────────────────────────────────────

# Profiles fully compatible with composite_bundle rendering.
BUNDLE_OK = {
    "generic-report", "risk", "tech", "creative", "cam",
    "mythic", "convergence", "keeper",
    "yugen-brand", "yugen-brand-elevated",
}

# Profiles partially compatible (template exists, renders documents,
# but missing one or more bundle features).
BUNDLE_PARTIAL: dict[str, list[str]] = {
    "mythic-letter-johannah": [
        "No TOC guard — --toc flag has no effect; TOC not rendered",
        "Missing \\tightlist — bullet lists cause XeLaTeX error",
        "Missing longtable support — tables may fail",
        "Custom font paths fragile (see G7 in gap report)",
    ],
    "letter": [
        "No TOC guard — --toc flag has no effect; TOC not rendered",
        "Memoir class — letter-centric layout, not designed for multi-section bundles",
        "Missing longtable support",
    ],
    "mythic-letter": [
        "No TOC guard — --toc flag has no effect; TOC not rendered",
        "Memoir class — letter-centric layout, not designed for multi-section bundles",
        "Missing longtable support",
    ],
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
        "Hardcoded campaign image assets — fails without real files",
        "No TOC guard — --toc flag has no effect",
        "Content-dependent (see G2 in gap report)",
        "Designed for single-packet Elian campaign render, not generic bundles",
    ],
    "elian-poster": [
        "Hardcoded campaign image assets — fails without real files",
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
    defaults_source: str = "missing"     # local | 40_latex | missing
    template_found: str | None = None   # resolved path, or None
    template_source: str = "missing"     # local | 40_latex | missing
    template_inferred: str = ""         # raw mapping lookup (before corrections)
    uses_40_latex: bool = True
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
            "uses_40_latex": self.uses_40_latex,
            "supports_toc": self.supports_toc,
            "has_tightlist": self.has_tightlist,
            "has_longtable": self.has_longtable,
            "bundle_compatibility": self.bundle_compatibility,
            "bundle_reasons": self.bundle_reasons,
            "warnings": self.warnings,
        }


# ── Checker ───────────────────────────────────────────────────────────────────


def check_profile(profile_id: str) -> ProfileCapability:
    """Check a single profile's capabilities against 40_latex resources."""

    cap = ProfileCapability(profile_id=profile_id)

    gf_root = Path(__file__).resolve().parents[1]
    local_import = gf_root / "profiles" / "40_latex_import"

    # ── defaults ──────────────────────────────────────────────────
    local_defaults, remote_defaults = _find_defaults_local_remote(profile_id, local_import)
    if local_defaults is not None:
        cap.defaults_found = str(local_defaults)
        cap.defaults_source = "local"
    elif remote_defaults is not None:
        cap.defaults_found = str(remote_defaults)
        cap.defaults_source = "40_latex"
    else:
        cap.defaults_found = None
        cap.defaults_source = "missing"
        cap.warnings.append(f"No defaults file found for {profile_id}")

    # ── template ──────────────────────────────────────────────────
    inferred = PROFILE_TEMPLATE_MAP.get(profile_id, "")
    cap.template_inferred = inferred

    effective_template = TEMPLATE_CORRECTIONS.get(profile_id, inferred)
    if not effective_template:
        cap.warnings.append(f"No template mapping for {profile_id}")
    else:
        local_tpath = local_import / "templates" / effective_template
        remote_tpath = LATEX40 / "templates" / effective_template
        uncorrected_tpath = LATEX40 / "templates" / inferred

        if local_tpath.exists():
            cap.template_found = str(local_tpath)
            cap.template_source = "local"
        elif remote_tpath.exists():
            cap.template_found = str(remote_tpath)
            cap.template_source = "40_latex"
        elif effective_template != inferred and uncorrected_tpath.exists():
            cap.template_found = str(uncorrected_tpath)
            cap.template_source = "40_latex"
            cap.warnings.append(
                f"Template mapping says {inferred} but {effective_template} "
                f"found (correction applied)"
            )
        else:
            cap.warnings.append(f"No template found for {profile_id} (expected {inferred})")

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
            f"check 40_latex/templates/"
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
            "target_40_latex_mutated": False,
            "reads_40_latex_readonly": True,
            "notes": (
                "This report reads 40_latex/defaults/*.yaml and "
                "40_latex/templates/*.tex as read-only references. "
                "No files are modified."
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
    remote_defaults = sum(1 for c in caps.values() if c.defaults_source == "40_latex")
    remote_templates = sum(1 for c in caps.values() if c.template_source == "40_latex")
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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _find_defaults_local_remote(profile_id: str, local_import: Path) -> tuple[Path | None, Path | None]:
    """Find defaults YAML for a profile, returning (local_path, remote_path)."""
    special: dict[str, str] = {
        "tech": "technology.yaml",
        "letter": "personal_letter.yaml",
        "mythic-letter": "personal_letter.yaml",
        "resume": "resume_resume.yaml",
        "prometheus-packet": "prometheus_packet.yaml",
        "yugen-brand": "yugenbase.yaml",
        "yugen-brand-elevated": "yugenbase.yaml",
        "labels-avery-15264": "labels_avery_5164.yaml",
    }
    patterns = [
        f"{profile_id}.yaml",
        f"{profile_id.replace('_', '-')}.yaml",
        f"{profile_id.replace('-', '_')}.yaml",
    ]
    if profile_id in special:
        patterns.insert(0, special[profile_id])

    local: Path | None = None
    remote: Path | None = None
    for p in patterns:
        lc = local_import / "defaults" / p
        if lc.exists() and local is None:
            local = lc
        rc = LATEX40 / "defaults" / p
        if rc.exists() and remote is None:
            remote = rc
    return local, remote


def _find_defaults(profile_id: str) -> Path | None:
    """Find defaults YAML for a profile, checking 40_latex then greenfield."""
    # 40_latex defaults/
    for pattern in [
        f"{profile_id}.yaml",
        f"{profile_id.replace('_', '-')}.yaml",
        f"{profile_id.replace('-', '_')}.yaml",
    ]:
        candidate = LATEX40 / "defaults" / pattern
        if candidate.exists():
            return candidate

    # Special-case known mappings that don't follow naming convention.
    special: dict[str, str] = {
        "tech": "technology.yaml",
        "letter": "personal_letter.yaml",
        "mythic-letter": "personal_letter.yaml",
        "resume": "resume_resume.yaml",
        "prometheus-packet": "prometheus_packet.yaml",
        "yugen-brand": "yugenbase.yaml",
        "yugen-brand-elevated": "yugenbase.yaml",
        "labels-avery-15264": "labels_avery_5164.yaml",
    }
    if profile_id in special:
        candidate = LATEX40 / "defaults" / special[profile_id]
        if candidate.exists():
            return candidate

    # Greenfield profiles/
    gf_root = Path(__file__).resolve().parents[1]
    for pdir_name in ("reports", "labels", "stickers", "letters", "resumes"):
        candidate = gf_root / "profiles" / pdir_name / f"{profile_id}.yaml"
        if candidate.exists():
            return candidate

    return None
