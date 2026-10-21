"""Tests for the single-object profile resolver seam."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.profile_resolver import resolve_profile


def test_document_spine_profile_is_neutral_base_profile():
    resolved = resolve_profile("document-spine")
    assert resolved.canonical_profile_id == "document-spine"
    assert resolved.profile_family == "document_spine"
    assert [p.name for p in resolved.defaults_stack] == ["document_spine.yaml"]
    assert resolved.template_path.name == "base.tex"


def test_tech_resolves_document_spine_yugen_overlay_and_technology_defaults():
    resolved = resolve_profile("tech")
    assert resolved.profile_id == "tech"
    assert resolved.canonical_profile_id == "yugen_tech"
    assert resolved.profile_family == "document_spine"
    assert [p.name for p in resolved.defaults_stack] == ["document_spine.yaml", "yugenbase.yaml", "technology.yaml"]
    assert resolved.template_path.name == "base.tex"
    assert resolved.boundary["target_legacy_profile_tree_mutated"] is False
    # A profile package since SIL-32: engine document_spine.yaml + package defaults, engine base.tex.
    assert resolved.boundary["defaults_source"] == "local+package"
    assert resolved.boundary["template_source"] == "local"


def test_risk_resolves_yugenbase_and_risk_defaults():
    resolved = resolve_profile("risk")
    assert resolved.canonical_profile_id == "yugen_risk"
    assert resolved.profile_family == "document_spine"
    assert [p.name for p in resolved.defaults_stack] == ["document_spine.yaml", "yugenbase.yaml", "risk.yaml"]
    assert resolved.template_path.name == "base.tex"


def test_civic_alias_resolves_to_yugen_civic_profile():
    resolved = resolve_profile("civic")
    assert resolved.profile_id == "civic"
    assert resolved.canonical_profile_id == "yugen_civic"
    assert resolved.profile_family == "document_spine"
    assert [p.name for p in resolved.defaults_stack] == ["document_spine.yaml", "yugenbase.yaml", "civic.yaml"]
    assert resolved.template_path.name == "base.tex"
    assert resolved.boundary["defaults_source"] == "local+package"  # a profile package since SIL-32
    assert resolved.boundary["template_source"] == "local"


def test_mythic_letter_is_stationery_art_not_document_spine():
    resolved = resolve_profile("mythic-letter")
    assert resolved.profile_family == "stationery_art"
    assert resolved.template_path.name == "personal_letter.tex"
    assert resolved.defaults_stack[-1].name == "mythic_letter.yaml"


def test_codex0_resolves_as_half_letter_johannah_mythic_book_profile():
    resolved = resolve_profile("codex0")
    assert resolved.profile_id == "codex0"
    assert resolved.canonical_profile_id == "codex0"
    assert resolved.profile_family == "document_spine"
    assert [p.name for p in resolved.defaults_stack] == [
        "document_spine.yaml",
        "personal_letter.yaml",
        "mythic_letter_johannah.yaml",
        "codex0.yaml",
    ]
    assert resolved.template_path.name == "codex0.tex"
    # Map G2: the codex0 profile package, on engine defaults.
    assert resolved.boundary["defaults_source"] == "local+package"
    assert resolved.boundary["template_source"] == "package"
    assert resolved.markers == {"prefix": "cx0"}


def test_codex0_a5_variant_preserves_compact_a5_profile():
    resolved = resolve_profile("codex0-a5")
    assert resolved.profile_id == "codex0-a5"
    assert resolved.canonical_profile_id == "codex0-a5"
    assert [p.name for p in resolved.defaults_stack] == ["document_spine.yaml", "yugenbase.yaml", "codex0_a5.yaml"]
    assert resolved.template_path.name == "codex0_a5.tex"


def test_packet_review_is_not_a_profile_family():
    resolved = resolve_profile("prometheus-packet")
    assert resolved.profile_family == "document_spine"
    assert resolved.profile_family != "packet_review"


def test_resolver_sets_local_import_environment():
    resolved = resolve_profile("tech")
    env = resolved.render_environment
    assert "profiles/40_latex_import/styles/texmf" in str(env.texmfhome)
    assert "profiles/40_latex_import" in str(env.cwd)
    assert any("profiles/40_latex_import/assets" in str(path) for path in resolved.asset_roots)
    assert any("profiles/40_latex_import" in str(path) for path in env.resource_paths)
    assert all("/Digital_Workspace/40_latex" not in str(path) for path in env.resource_paths)
    assert "/Digital_Workspace/40_latex" not in env.texinputs
    assert resolved.boundary["uses_local_imports"] is True
    assert resolved.boundary["reads_legacy_profile_tree"] is False
    assert resolved.boundary["target_legacy_profile_tree_mutated"] is False
