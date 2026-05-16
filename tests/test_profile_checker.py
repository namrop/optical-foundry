"""Tests for engine.profile_checker — profile capability inventory."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.profile_checker import (
    check_profile,
    check_all_profiles,
    check_all_profiles_json,
    PROFILE_IDS,
    BUNDLE_OK,
    BUNDLE_PARTIAL,
    BUNDLE_INCOMPATIBLE,
    TOC_GUARD_PROFILES,
    TIGHTLIST_PROFILES,
    LONGTABLE_PROFILES,
)


# ── Structural tests ────────────────────────────────────────────


def test_all_profile_ids_have_classification():
    """Every known profile must be in exactly one bundle compatibility bucket."""
    classified = set(BUNDLE_OK) | set(BUNDLE_PARTIAL) | set(BUNDLE_INCOMPATIBLE)
    for pid in PROFILE_IDS:
        assert pid in classified, (
            f"Profile '{pid}' not classified in BUNDLE_OK, BUNDLE_PARTIAL, or BUNDLE_INCOMPATIBLE"
        )


def test_no_overlap_in_classifications():
    """No profile should be in more than one bundle compatibility bucket."""
    ok_set = set(BUNDLE_OK)
    partial_set = set(BUNDLE_PARTIAL)
    incompatible_set = set(BUNDLE_INCOMPATIBLE)
    assert ok_set.isdisjoint(partial_set)
    assert ok_set.isdisjoint(incompatible_set)
    assert partial_set.isdisjoint(incompatible_set)


# ── Specific profile tests ──────────────────────────────────────


def test_generic_report_is_bundle_ok():
    cap = check_profile("generic-report")
    assert cap.bundle_compatibility == "ok"
    assert cap.supports_toc is True
    assert cap.has_tightlist is True
    assert cap.has_longtable is True
    assert cap.defaults_found is not None, f"Expected defaults for generic-report, got None"
    assert cap.template_found is not None, f"Expected template for generic-report, got None"
    assert cap.warnings == [], f"Unexpected warnings: {cap.warnings}"


def test_cam_is_bundle_ok():
    cap = check_profile("cam")
    assert cap.bundle_compatibility == "ok"
    assert cap.supports_toc is True
    assert cap.has_tightlist is True
    assert cap.has_longtable is True
    assert cap.defaults_found is not None
    assert cap.template_found is not None


def test_yugen_civic_is_bundle_ok():
    cap = check_profile("yugen-civic")
    assert cap.bundle_compatibility == "ok"
    assert cap.supports_toc is True
    assert cap.has_tightlist is True
    assert cap.has_longtable is True
    assert cap.defaults_found is not None
    assert cap.defaults_found.endswith("/civic.yaml")
    assert cap.template_found is not None
    assert cap.template_found.endswith("/base.tex")
    assert cap.defaults_source == "local"
    assert cap.template_source == "local"
    assert cap.warnings == []


def test_mythic_letter_johannah_is_bundle_ok():
    cap = check_profile("mythic-letter-johannah")
    assert cap.bundle_compatibility == "ok"
    assert cap.supports_toc is True
    assert cap.has_tightlist is True
    assert cap.has_longtable is True
    assert cap.defaults_found is not None
    assert cap.template_found is not None
    assert cap.defaults_source == "local"
    assert cap.template_source == "local"


def test_letter_is_bundle_ok():
    cap = check_profile("letter")
    assert cap.bundle_compatibility == "ok"
    assert cap.supports_toc is True
    assert cap.has_tightlist is True
    assert cap.has_longtable is True
    assert cap.template_found is not None
    assert cap.defaults_source == "local"
    assert cap.template_source == "local"


def test_mythic_letter_is_bundle_ok():
    cap = check_profile("mythic-letter")
    assert cap.bundle_compatibility == "ok"
    assert cap.supports_toc is True
    assert cap.has_tightlist is True
    assert cap.has_longtable is True
    assert cap.template_found is not None
    assert cap.defaults_source == "local"
    assert cap.template_source == "local"


def test_elian_packet_is_incompatible():
    cap = check_profile("elian-packet")
    assert cap.bundle_compatibility == "incompatible"
    assert cap.supports_toc is False
    reasons_text = " ".join(cap.bundle_reasons).lower()
    assert "campaign" in reasons_text or "asset" in reasons_text or "content" in reasons_text


def test_elian_poster_is_incompatible():
    cap = check_profile("elian-poster")
    assert cap.bundle_compatibility == "incompatible"
    assert cap.supports_toc is False
    assert cap.has_tightlist is False
    assert cap.has_longtable is False


def test_labels_avery_5164_is_incompatible():
    cap = check_profile("labels-avery-5164")
    assert cap.bundle_compatibility == "incompatible"
    assert cap.supports_toc is False


def test_sticker_sheet_is_incompatible():
    cap = check_profile("sticker-sheet")
    assert cap.bundle_compatibility == "incompatible"
    assert cap.supports_toc is False


def test_resume_is_partial():
    cap = check_profile("resume")
    assert cap.bundle_compatibility == "partial"
    assert cap.supports_toc is False
    assert cap.has_tightlist is True  # resume.tex has tightlist


def test_prometheus_packet_is_partial():
    cap = check_profile("prometheus-packet")
    assert cap.bundle_compatibility == "partial"
    assert cap.supports_toc is True  # uses generic_report.tex which has TOC guard


# ── Bulk check tests ────────────────────────────────────────────


def test_check_all_profiles_returns_all():
    caps = check_all_profiles()
    assert len(caps) == len(PROFILE_IDS)
    for pid in PROFILE_IDS:
        assert pid in caps, f"Missing profile {pid} in check_all_profiles result"


def test_check_all_profiles_json_is_valid():
    data = check_all_profiles_json()
    report = json.loads(data)
    assert report["schema_version"] == "profile_capability_check_v1"
    assert report["profiles_checked"] == len(PROFILE_IDS)
    assert "summary" in report
    s = report["summary"]
    assert s["total"] == len(PROFILE_IDS)
    assert s["bundle_ok"] + s["bundle_partial"] + s["bundle_incompatible"] == s["total"]
    for pid in PROFILE_IDS:
        assert pid in report["profiles"], f"Missing {pid} in JSON report"


# ── Edge cases ──────────────────────────────────────────────────


def test_unknown_profile_reports_unknown():
    cap = check_profile("nonexistent-profile-999")
    assert cap.bundle_compatibility == "incompatible"
    assert cap.template_found is None
    assert cap.defaults_found is None
    assert cap.supports_toc is False


def test_defaults_found_is_absolute_path():
    cap = check_profile("generic-report")
    if cap.defaults_found:
        assert cap.defaults_found.startswith("/"), (
            f"Expected absolute path for defaults, got: {cap.defaults_found}"
        )


def test_template_found_is_absolute_path():
    cap = check_profile("generic-report")
    if cap.template_found:
        assert cap.template_found.startswith("/"), (
            f"Expected absolute path for template, got: {cap.template_found}"
        )


# ── Source detection tests ──────────────────────────────────────


def test_generic_report_sources_are_local():
    """With 40_latex_import directory present, profile assets should be local."""
    cap = check_profile("generic-report")
    assert cap.defaults_source == "local", (
        f"Expected defaults_source='local', got '{cap.defaults_source}'"
    )
    assert cap.template_source == "local", (
        f"Expected template_source='local', got '{cap.template_source}'"
    )
    assert "40_latex_import" in cap.defaults_found, (
        f"Expected local import path, got: {cap.defaults_found}"
    )
    assert "40_latex_import" in cap.template_found, (
        f"Expected local import path, got: {cap.template_found}"
    )


def test_all_bundle_ok_profiles_have_local_sources():
    """All bundle-ok profiles should resolve assets from local import."""
    from engine.profile_checker import BUNDLE_OK
    caps = check_all_profiles()
    for pid in BUNDLE_OK:
        cap = caps[pid]
        assert cap.defaults_source == "local", (
            f"{pid}: expected defaults_source='local', got '{cap.defaults_source}'"
        )
        assert cap.template_source == "local", (
            f"{pid}: expected template_source='local', got '{cap.template_source}'"
        )


def test_json_report_includes_source_fields():
    data = check_all_profiles_json()
    report = __import__("json").loads(data)
    caps = report["profiles"]
    for pid, cap in caps.items():
        assert "defaults_source" in cap, f"Missing defaults_source for {pid}"
        assert "template_source" in cap, f"Missing template_source for {pid}"
        assert cap["defaults_source"] in ("local", "missing"), (
            f"{pid}: invalid defaults_source '{cap['defaults_source']}'"
        )
        assert cap["template_source"] in ("local", "missing"), (
            f"{pid}: invalid template_source '{cap['template_source']}'"
        )


def test_summary_includes_source_counts():
    data = check_all_profiles_json()
    report = __import__("json").loads(data)
    s = report["summary"]
    # At least some should be local since we have the import dir
    assert s["defaults_local"] == s["with_defaults"]
    assert s["templates_local"] == s["with_templates"]
    assert s.get("defaults_40_latex", 0) == 0
    assert s.get("templates_40_latex", 0) == 0


def test_unknown_profile_source_is_missing():
    cap = check_profile("nonexistent-profile-999")
    assert cap.defaults_source == "missing"
    assert cap.template_source == "missing"
