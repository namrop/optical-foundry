"""Report frontmatter contract — validation and resolution for report profiles.

The client report profile accepts a small, validated frontmatter contract so
that document classification, cover metadata, figure caption/numbering behavior,
footers, PDF metadata, and the embedded-artifact filename all resolve from
authored settings rather than profile constants. This module is the single
source of truth for that contract: the enum→label maps, the defaults, and the
warning/error policy.

Design boundaries:
- Brand/template-coupled behavior (classification default, footer default,
  cover kicker/version block, unknown-field warnings) is gated to
  ``REPORT_PROFILES`` so non-report profiles are untouched.
- Figure caption/numbering resolution applies to *every* profile, because the
  underlying default (no auto-invented caption) is a renderer-wide correction,
  not a brand choice.

The resolved object is threaded onto ``ProjectionPlan.document_settings`` and
lowered by the Pandoc renderer into ``-V``/``-M`` flags and template variables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


# ── Enum → canonical display label maps (single source of truth) ─────────────

CLASSIFICATION_LABELS: dict[str, str] = {
    "public": "PUBLIC",
    "internal": "INTERNAL",
    "confidential": "CONFIDENTIAL",
    "highly-confidential": "HIGHLY CONFIDENTIAL",
}

DOCUMENT_STATUS_LABELS: dict[str, str] = {
    "draft": "DRAFT",
    "final": "FINAL",
}

# Profiles that opt into the full report contract (brand defaults + validation).
REPORT_PROFILES: frozenset[str] = frozenset({"client_report"})

DEFAULT_CLASSIFICATION = "highly-confidential"
DEFAULT_LANG = "en-US"
DEFAULT_DOCUMENT_TYPE = "SECURITY REPORT"
DEFAULT_FOOTER_CENTER = "CLIENT"
DEFAULT_TOC_TITLE = "Contents"

# Frontmatter keys recognized by the report contract or the shared document
# lane. Unrecognized keys draw an "ignored" warning (report profiles only) so
# that a silently-dropped security-relevant field is surfaced rather than lost.
RECOGNIZED_KEYS: frozenset[str] = frozenset(
    {
        # Shared document/cover fields.
        "uid",
        "title",
        "subtitle",
        "author",
        "date",
        "abstract",
        # TOC / numbering.
        "toc",
        "toc-depth",
        "toc-title",
        "numbersections",
        # Report contract.
        "classification",
        "classification-display",
        "document-status",
        "document-type",
        "version",
        "prepared-for",
        "subject",
        "keywords",
        "lang",
        "figure-captions",
        "figure-numbering",
        "figure-numbering-scope",
        "footer-center",
        "footer-right",
        "papersize",
        "artifact-name",
    }
)

# Geometry/margin keys the report profile owns and therefore ignores if the
# author supplies them. Surfaced as a warning rather than silently dropped.
PROFILE_OWNED_GEOMETRY_KEYS: frozenset[str] = frozenset(
    {"geometry", "margin", "margins", "page-margins"}
)


class ReportSettingsError(ValueError):
    """Fatal report-frontmatter error (e.g. an unknown enumerated value)."""


@dataclass(frozen=True)
class ReportSettings:
    """Resolved report frontmatter, ready to lower into pandoc + template."""

    is_report: bool = False
    classification: str = ""
    classification_label: str = ""
    classification_display: bool = True
    document_status: str = ""
    document_status_label: str = ""
    document_type: str = ""
    footer_center: str = ""
    footer_right: str = ""
    version: str = ""
    prepared_for: str = ""
    subject: str = ""
    keywords: str = ""
    lang: str = ""
    toc_title: str = ""
    figure_captions: bool = False
    figure_numbering: bool = False
    figure_numbering_section: bool = False
    artifact_name: str = ""

    def template_variables(self) -> dict[str, str]:
        """Pandoc ``-V`` presentation variables consumed by the template."""
        variables: dict[str, str] = {}
        if self.classification_display and self.classification_label:
            variables["classification_label"] = self.classification_label
        elif self.is_report and not self.classification_display:
            # display:none — force the marking empty so neither the cover label
            # nor the running header prints a classification.
            variables["classification_suppressed"] = "true"
        if self.document_status_label:
            variables["document_status"] = self.document_status_label
        if self.document_type:
            variables["document_type"] = self.document_type
        if self.footer_center:
            variables["footer_center"] = self.footer_center
        if self.footer_right:
            variables["footer_right"] = self.footer_right
        if self.version:
            variables["version"] = self.version
        if self.prepared_for:
            variables["prepared_for"] = self.prepared_for
        if self.toc_title:
            variables["toc-title"] = self.toc_title
        if self.figure_numbering_section:
            variables["figure_numbering_section"] = "true"
        return variables

    def metadata(self) -> dict[str, str]:
        """Pandoc ``-M`` metadata (native fields → PDF docinfo/XMP + lang)."""
        meta: dict[str, str] = {}
        if self.subject:
            meta["subject"] = self.subject
        if self.keywords:
            meta["keywords"] = self.keywords
        if self.lang:
            meta["lang"] = self.lang
        return meta

    def evidence(self) -> dict[str, Any]:
        """Resolved values surfaced into the render evidence / MCP response."""
        return {
            "resolved_classification": self.classification,
            "resolved_document_status": self.document_status,
        }


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "on", "1"}
    if value is None:
        return default
    return bool(value)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _join_keywords(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_as_str(item) for item in value if _as_str(item))
    return _as_str(value)


_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_artifact_name(value: str) -> str:
    """Reduce a caller-provided name to a safe, basename-only ``.pdf`` filename.

    The result affects only the embedded MCP resource filename, never a
    server-side output path. Path separators and unsafe characters collapse to
    hyphens; a ``.pdf`` suffix is enforced.
    """
    # Basename only — strip any directory components a caller may have supplied.
    base = str(value).replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = _SANITIZE_RE.sub("-", base).strip("-._")
    if not base:
        base = "report"
    if base.lower().endswith(".pdf"):
        base = base[:-4].strip("-._") or "report"
    return f"{base}.pdf"


def resolve_report_settings(
    frontmatter: dict[str, Any],
    *,
    canonical_profile_id: str,
) -> tuple[ReportSettings, list[str]]:
    """Resolve + validate report frontmatter into a ``ReportSettings`` object.

    Returns ``(settings, warnings)``. Raises ``ReportSettingsError`` on a fatal
    problem such as an unknown enumerated value.
    """
    fm = frontmatter if isinstance(frontmatter, dict) else {}
    is_report = canonical_profile_id in REPORT_PROFILES
    warnings: list[str] = []

    # ── Figure caption / numbering (all profiles) ────────────────────────────
    figure_captions = _as_bool(fm.get("figure-captions"), default=False)
    figure_numbering = _as_bool(fm.get("figure-numbering"), default=False)
    scope = _as_str(fm.get("figure-numbering-scope")).lower()
    if scope and scope not in {"global", "section"}:
        warnings.append(
            f"figure-numbering-scope '{scope}' unrecognized; using global numbering"
        )
        scope = ""
    figure_numbering_section = scope == "section"

    # ── artifact-name (all profiles) ─────────────────────────────────────────
    artifact_source = _as_str(fm.get("artifact-name")) or _as_str(fm.get("title")) or "report"
    artifact_name = sanitize_artifact_name(artifact_source)

    if not is_report:
        return (
            ReportSettings(
                is_report=False,
                figure_captions=figure_captions,
                figure_numbering=figure_numbering,
                figure_numbering_section=figure_numbering_section,
                artifact_name=artifact_name,
            ),
            warnings,
        )

    # ── Classification (report profiles) ─────────────────────────────────────
    raw_classification = fm.get("classification")
    classification = _as_str(raw_classification).lower()
    if raw_classification is None or classification == "":
        classification = DEFAULT_CLASSIFICATION
        warnings.append(
            "classification not set; defaulting to highly-confidential "
            "(the most restrictive marking)"
        )
    elif classification not in CLASSIFICATION_LABELS:
        # A legacy combined value such as "Public Draft" carries the
        # classification in its first token — recover it and warn rather than
        # silently mismarking the document.
        first = classification.split()[0] if classification.split() else ""
        if first in CLASSIFICATION_LABELS:
            warnings.append(
                f"legacy combined classification value {raw_classification!r} could not be "
                f"mapped cleanly; using classification: {first} — set document-status separately"
            )
            classification = first
        else:
            raise ReportSettingsError(
                f"unknown classification {raw_classification!r}; expected one of "
                + ", ".join(sorted(CLASSIFICATION_LABELS))
            )
    classification_label = CLASSIFICATION_LABELS[classification]

    classification_display = True
    if _as_str(fm.get("classification-display")).lower() == "none":
        classification_display = False

    # ── Document status (separate from classification) ───────────────────────
    raw_status = fm.get("document-status")
    document_status = _as_str(raw_status).lower()
    document_status_label = ""
    if document_status:
        if document_status not in DOCUMENT_STATUS_LABELS:
            raise ReportSettingsError(
                f"unknown document-status {raw_status!r}; expected one of "
                + ", ".join(sorted(DOCUMENT_STATUS_LABELS))
            )
        document_status_label = DOCUMENT_STATUS_LABELS[document_status]

    # ── Cover / footer / PDF metadata ────────────────────────────────────────
    document_type = _as_str(fm.get("document-type")) or DEFAULT_DOCUMENT_TYPE
    footer_center = _as_str(fm.get("footer-center")) or DEFAULT_FOOTER_CENTER
    footer_right = _as_str(fm.get("footer-right"))
    version = _as_str(fm.get("version"))
    prepared_for = _as_str(fm.get("prepared-for"))
    subject = _as_str(fm.get("subject"))
    keywords = _join_keywords(fm.get("keywords"))
    lang = _as_str(fm.get("lang")) or DEFAULT_LANG
    toc_title = _as_str(fm.get("toc-title")) or DEFAULT_TOC_TITLE

    # ── Ignored / unrecognized field warnings ────────────────────────────────
    for key in fm:
        if not isinstance(key, str):
            continue
        if key in PROFILE_OWNED_GEOMETRY_KEYS:
            warnings.append(
                f"{key!r} ignored: the client_report profile owns page geometry"
            )
        elif key not in RECOGNIZED_KEYS and key != "variables":
            warnings.append(f"unrecognized frontmatter field {key!r} was ignored")

    settings = ReportSettings(
        is_report=True,
        classification=classification,
        classification_label=classification_label,
        classification_display=classification_display,
        document_status=document_status,
        document_status_label=document_status_label,
        document_type=document_type,
        footer_center=footer_center,
        footer_right=footer_right,
        version=version,
        prepared_for=prepared_for,
        subject=subject,
        keywords=keywords,
        lang=lang,
        toc_title=toc_title,
        figure_captions=figure_captions,
        figure_numbering=figure_numbering,
        figure_numbering_section=figure_numbering_section,
        artifact_name=artifact_name,
    )
    return settings, warnings
