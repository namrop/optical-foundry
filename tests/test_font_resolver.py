from pathlib import Path

from engine.profile_resolver import LOCAL_IMPORT, resolve_profile
from engine.font_resolver import resolve_profile_fonts


def _by_role(fonts):
    return {entry["role"]: entry for entry in fonts["fonts"]}


def test_document_spine_fonts_are_declared_system_fallbacks_not_silent_dependencies():
    resolved = resolve_profile("document-spine")

    fonts = resolve_profile_fonts(resolved)
    by_role = _by_role(fonts)

    assert fonts["policy"] == "foundry_local_first_declared_system_fallback"
    assert by_role["mainfont"]["requested"] == "Helvetica"
    assert by_role["mainfont"]["status"] == "declared_system_fallback"
    assert by_role["monofont"]["requested"] == "Menlo"
    assert by_role["monofont"]["status"] == "declared_system_fallback"
    assert all("/40_latex/" not in str(entry.get("resolved_path", "")) for entry in fonts["fonts"])


def test_mythic_johannah_header_font_resolves_to_foundry_local_asset():
    resolved = resolve_profile("mythic-letter-johannah")

    fonts = resolve_profile_fonts(resolved)
    by_role = _by_role(fonts)

    header = by_role["stationery_header_font"]
    assert header["requested"] == "MeaCulpa-Regular.ttf"
    assert header["status"] == "foundry_local"
    assert Path(header["resolved_path"]) == LOCAL_IMPORT / "assets" / "fonts" / "mythic_letter" / "MeaCulpa-Regular.ttf"
    assert header["source"] == "defaults:mythic_letter_johannah.yaml"


def test_resolved_profile_carries_font_policy_evidence():
    resolved = resolve_profile("creative")

    assert resolved.font_policy["policy"] == "foundry_local_first_declared_system_fallback"
    roles = {entry["role"] for entry in resolved.font_policy["fonts"]}
    assert {"mainfont", "sansfont", "monofont"}.issubset(roles)
    assert resolved.boundary["font_policy"] == "foundry_local_first_declared_system_fallback"
