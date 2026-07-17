"""Tests for the report frontmatter contract (engine.report_settings)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engine.report_settings import (
    ReportSettingsError,
    resolve_report_settings,
    sanitize_artifact_name,
)

REPORT = "client_report"


def _resolve(fm, profile=REPORT):
    return resolve_report_settings(fm, canonical_profile_id=profile)


def test_classification_enum_to_label():
    for key, label in [
        ("public", "PUBLIC"),
        ("internal", "INTERNAL"),
        ("confidential", "CONFIDENTIAL"),
        ("highly-confidential", "HIGHLY CONFIDENTIAL"),
    ]:
        s, warnings = _resolve({"title": "X", "classification": key})
        assert s.classification == key
        assert s.classification_label == label
        assert warnings == []


def test_absent_classification_defaults_with_warning():
    s, warnings = _resolve({"title": "X"})
    assert s.classification == "highly-confidential"
    assert s.classification_label == "HIGHLY CONFIDENTIAL"
    assert any("defaulting to highly-confidential" in w for w in warnings)


def test_unknown_classification_raises():
    with pytest.raises(ReportSettingsError):
        _resolve({"classification": "top-secret"})


def test_unknown_document_status_raises():
    with pytest.raises(ReportSettingsError):
        _resolve({"title": "X", "classification": "public", "document-status": "provisional"})


def test_document_status_resolves():
    s, _ = _resolve({"title": "X", "classification": "public", "document-status": "draft"})
    assert s.document_status == "draft"
    assert s.document_status_label == "DRAFT"


def test_classification_display_none_suppresses_marking():
    s, _ = _resolve({"title": "X", "classification": "public", "classification-display": "none"})
    assert s.classification_display is False
    tvars = s.template_variables()
    assert "classification_label" not in tvars
    assert tvars.get("classification_suppressed") == "true"


def test_legacy_combined_value_warns_and_recovers():
    s, warnings = _resolve({"title": "X", "classification": "Public Draft"})
    assert s.classification == "public"
    assert any("legacy combined" in w for w in warnings)


def test_footer_and_document_type_defaults():
    s, _ = _resolve({"title": "X", "classification": "internal"})
    assert s.footer_center == "CLIENT"
    assert s.document_type == "SECURITY REPORT"
    s2, _ = _resolve({"title": "X", "classification": "internal",
                      "footer-center": "CLIENT LABS", "document-type": "CLIENT REPORT"})
    assert s2.footer_center == "CLIENT LABS"
    assert s2.document_type == "CLIENT REPORT"


def test_keywords_list_joins_and_metadata():
    s, _ = _resolve({"title": "X", "classification": "public",
                     "keywords": ["Client", "Slingshot"], "subject": "Sub", "lang": "en-GB"})
    assert s.keywords == "Client, Slingshot"
    meta = s.metadata()
    assert meta["keywords"] == "Client, Slingshot"
    assert meta["subject"] == "Sub"
    assert meta["lang"] == "en-GB"


def test_unrecognized_and_geometry_field_warnings():
    s, warnings = _resolve({"title": "X", "classification": "internal", "geometry": "x", "bogus": 1})
    assert any("geometry" in w and "owns page geometry" in w for w in warnings)
    assert any("bogus" in w and "ignored" in w for w in warnings)


def test_figure_numbering_scope_section():
    s, _ = _resolve({"title": "X", "classification": "internal",
                     "figure-numbering": True, "figure-numbering-scope": "section"})
    assert s.figure_numbering is True
    assert s.figure_numbering_section is True
    assert s.template_variables().get("figure_numbering_section") == "true"


def test_non_report_profile_only_figure_settings():
    s, warnings = _resolve({"title": "X", "classification": "whatever", "figure-captions": True}, profile="cam")
    assert s.is_report is False
    assert s.figure_captions is True
    assert s.classification_label == ""   # classification not applied for non-report
    assert warnings == []                 # no unknown-field noise on non-report


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("slingshot report/x.pdf", "x.pdf"),
        ("../../etc/passwd", "passwd.pdf"),
        ("My Report 2026", "My-Report-2026.pdf"),
        ("", "report.pdf"),
        ("already.pdf", "already.pdf"),
    ],
)
def test_sanitize_artifact_name(raw, expected):
    assert sanitize_artifact_name(raw) == expected


def test_artifact_name_from_title_when_absent():
    s, _ = _resolve({"title": "Slingshot Summary", "classification": "public"})
    assert s.artifact_name == "Slingshot-Summary.pdf"
    s2, _ = _resolve({"title": "X", "classification": "public",
                      "artifact-name": "custom-name.pdf"})
    assert s2.artifact_name == "custom-name.pdf"
