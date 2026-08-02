"""Manifest compiler base and concrete compilers.

A ManifestCompiler validates a typed render manifest and produces a
ProjectionPlan. Each supported (kind, schema_version) pair should have one
dedicated compiler registered through the ManifestRegistry.

Concrete compilers:
  - CompositeBundleCompiler: composite_bundle / bundle_manifest_v1
  - CAMStackCompiler:        cam_stack / bundle_manifest_v1
  - CodexBundleCompiler:     codex_bundle / bundle_manifest_v1
  - LabelRunCompiler:        label_run / label_run_v1
  - StickerSheetCompiler:    sticker_sheet / sticker_sheet_v1
  - ForgePacketReviewCompiler: forge_packet_review / packet_review_manifest_v1
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from engine.render_planner import RenderPlan, plan_manifest_render
from engine.projection_plan import AssemblyView, ProjectionPlan
from engine.profile_resolver import resolve_profile
from engine.page_size import (
    PageMarginError,
    PageSizeError,
    page_margins_from_mapping,
    page_size_from_mapping,
    profile_default_page_size,
)
from engine.delivery import (
    bound_colophon_block,
    delivery_boundary,
    delivery_page_margins,
    insert_title_verso_colophon,
    inject_bound_illumination_rail_marks,
    normalize_delivery,
    suppress_bound_pagination_overrides,
    inject_bound_running_header_marks,
    validate_delivery,
)


class ManifestCompiler(ABC):
    """Base for all manifest compilers.

    Subclasses must define `compile` and `validate`.
    """

    kind: str = ""
    schema_version: str = ""

    @abstractmethod
    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        """Validate the manifest and produce a ProjectionPlan."""

    @abstractmethod
    def validate(self, manifest: dict[str, Any]) -> list[str]:
        """Return a list of validation errors (empty = valid)."""


class NullCompiler(ManifestCompiler):
    """Identity compiler used when the input is a plain Markdown document.

    This compiler exists so the render dispatch can treat Markdown documents
    as a degenerate manifest case without special-casing the dispatch path.
    """

    kind = "_document"
    schema_version = "_document_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        raise NotImplementedError("NullCompiler is a bypass marker, not an executable compiler")

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        return []


# Module-level singleton for the identity bypass.
null_compiler = NullCompiler()


# ──────────────────────────────────────────────
#  Helpers shared across compilers
# ──────────────────────────────────────────────


def _sha256_hex(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _profile_default_page_size_for(profile_id: str) -> tuple[str, str]:
    """Return a profile-authored page size, falling back to letter/default."""

    try:
        return profile_default_page_size(resolve_profile(profile_id).defaults_stack)
    except Exception:
        return "letter", "default"


def _split_frontmatter_and_body(text: str) -> tuple[dict[str, Any] | None, str]:
    """Split YAML frontmatter from Markdown body.

    Returns (parsed_dict_or_None, body_str). Returns (None, text) if no
    frontmatter is detected or parsing fails.
    """
    try:
        import yaml
    except ImportError:
        return None, text

    text = text.lstrip()
    if not text.startswith("---"):
        return None, text

    idx = text.find("---", 3)
    if idx == -1:
        return None, text

    fm_block = text[3:idx].strip()
    body = text[idx + 3 :]

    try:
        fm = yaml.safe_load(fm_block)
    except yaml.YAMLError:
        return None, text

    return fm if isinstance(fm, dict) else None, body


def _demote_headings(body: str, levels: int = 2) -> str:
    """Demote all ATX headings by `levels` to prevent source headings from
    competing with the assembly-level section heading."""
    import re

    def _demote(m: re.Match) -> str:
        hashes = m.group(1)
        if len(hashes) + levels > 6:
            return "######" + m.group(2)
        return ("#" * (len(hashes) + levels)) + m.group(2)

    return re.sub(r"^(#{1,6})( .*)$", _demote, body, flags=re.MULTILINE)


_CX0_MARKER_RE = re.compile(r"^\s*<!--\s*cx0:([\w-]+).*?-->\s*$")

# cx0 markers that render a visible passage-level separator. A body opening with
# one of these already carries its own break, so the compiler must not stack an
# injected passage separator on top. Register/edition-selection markers
# (`cx0:variant`, `cx0:edition`, `cx0:endvariant`) are invisible control markers
# — they do NOT count as an authored separator, so a passage opening with one
# still receives its injected boundary mark.
_CX0_ORNAMENT_MARKERS = frozenset(
    {"breath", "hinge", "major-hinge", "tailpiece", "threshold", "landing", "rule"}
)


def _body_opens_with_cx0_marker(body: str) -> bool:
    """True if the first non-blank line of a source body is an authored cx0
    ornament separator (e.g. `<!-- cx0:breath -->`). Used to avoid stacking a
    compiler-inserted passage separator on top of an author's explicit one.
    Invisible control markers (cx0:variant/edition) do not count."""
    for line in body.lstrip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _CX0_MARKER_RE.match(stripped)
        return bool(m and m.group(1) in _CX0_ORNAMENT_MARKERS)
    return False


_SUPPORTED_CODEX_SOURCE_REGISTERS = frozenset({"pataphorical"})


def _wrap_codex_source_register(body: str, register: str) -> str:
    """Wrap one assembled source body in its validated Codex semantic register."""

    normalized = str(register or "").strip().lower()
    if normalized not in _SUPPORTED_CODEX_SOURCE_REGISTERS:
        raise ValueError(f"unsupported codex source register: {register!r}")
    return (
        f'::: {{.codex-{normalized} register="{normalized}"}}\n'
        f"{body.rstrip()}\n"
        ":::"
    )


def _write_temp_markdown(prefix: str, content: str) -> Path:
    """Write assembled Markdown to a named temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".md", prefix=f"of_{prefix}_")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return Path(path)


def _apply_manifest_resolution(manifest: dict[str, Any], assembly: AssemblyView) -> tuple[RenderPlan, dict[str, dict[str, Any]]]:
    """Populate assembly-family fields and return child profile evidence by object id."""

    render_plan = plan_manifest_render(manifest)
    resolved = render_plan.manifest
    if resolved is None:
        return render_plan, {}

    assembly.manifest_family = resolved.manifest_family
    assembly.manifest_subtype = resolved.manifest_subtype
    assembly.assembly_strategy = resolved.assembly_strategy
    assembly.numbering_strategy = resolved.numbering_strategy

    child_profiles: list[dict[str, Any]] = []
    for child in render_plan.children:
        evidence = {
            "object_id": child.object_id,
            "source_path": str(child.source_path) if child.source_path else "",
            "role": child.role,
            "order": child.order,
            "requested_profile_id": child.requested_profile_id,
            "requested_profile_family": child.requested_profile_family,
            "resolved_profile_id": child.resolved_profile.canonical_profile_id,
            "resolved_profile_request_id": child.resolved_profile.profile_id,
            "profile_family": child.resolved_profile.profile_family,
            "defaults_stack": [path.name for path in child.resolved_profile.defaults_stack],
            "template": child.resolved_profile.template_path.name,
        }
        child_profiles.append(evidence)

    assembly.child_profiles = child_profiles
    return render_plan, {entry["object_id"]: entry for entry in child_profiles}


def _manifest_boundary_assertions(render_plan: RenderPlan) -> dict[str, Any]:
    resolved = render_plan.manifest
    assembly = render_plan.assembly
    if resolved is None or assembly is None:
        return {}
    return {
        "manifest_family": resolved.manifest_family,
        "manifest_subtype": resolved.manifest_subtype,
        "assembly_strategy": assembly.strategy,
        "numbering_strategy": assembly.numbering_strategy,
        **resolved.boundary,
    }


def _inventory_profile_fields(child_profile_by_id: dict[str, dict[str, Any]], uid: str) -> dict[str, Any]:
    child = child_profile_by_id.get(uid)
    if child is None:
        return {}
    return {
        "requested_profile_id": child.get("requested_profile_id"),
        "requested_profile_family": child.get("requested_profile_family"),
        "resolved_profile_id": child.get("resolved_profile_id"),
        "profile_family": child.get("profile_family"),
    }


# ──────────────────────────────────────────────
#  Concrete manifest compilers
# ──────────────────────────────────────────────


DOCUMENT_VARIABLE_ALLOWLIST = {
    "sample",
    "draft",
    "titlepage",
    "titlepage_background_image",
    "titlepage_blank_after",
    "logo_path",
    "division",
    "tagline",
    "footeremail",
    "footer_email",
    "chart_primary",
    "chart_accent",
    "chart_secondary",
    "chart_background",
    "chart_surface",
    "chart_text",
    "chart_muted",
    "codex_edition",
    "codex_strip_editorial_callouts",
    # Per-volume designation for the Codex 0 three-volume split (OF issue 22).
    # A short label ("Volume I") the codex0 template lowers to \CodexVolume,
    # printed on the half-title and title page of each volume.
    "codex_volume",
    # Optional arabic folio assigned immediately after memoir's \mainmatter reset.
    # This lets a later physical volume continue the reading-volume folio sequence
    # while keeping its own independent roman-numbered frontmatter.
    "body_folio_start",
    # Colophon prose-word measure, computed by the codex0 spine-projection tool
    # at bundle time and substituted into the colophon's <<COLOPHON_WORDS>>
    # placeholder by the codex0 template's intermediate assembly step.
    "colophon_words",
}

RUNNING_TEXT_KEY_ALIASES = {
    "division": "division",
    "header": "division",
    "header_right": "division",
    "tagline": "tagline",
    "footer": "footeremail",
    "footer_right": "footeremail",
    "footeremail": "footeremail",
    "footer_email": "footeremail",
}
RUNNING_TEXT_CANONICAL_ORDER = ("division", "tagline", "footeremail")

RESOURCE_PATH_VARIABLES = {"logo_path", "titlepage_background_image"}
RESOURCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

LATEX_INJECTION_TOKENS = ("\\input", "\\include", "\\write", "\\openout", "\\catcode", "\\usepackage")



def _safe_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _safe_template_string(value: str) -> bool:
    lowered = value.lower()
    return not any(token in lowered for token in LATEX_INJECTION_TOKENS)


def _safe_render_resource_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\x00" in value or "://" in value:
        return False
    if any(ch in value for ch in ("{", "}", "$", "`")):
        return False
    path = Path(value)
    if path.is_absolute():
        return False
    if ".." in path.parts:
        return False
    return path.suffix.lower() in RESOURCE_IMAGE_EXTENSIONS


def _safe_logo_path(value: Any) -> bool:
    return _safe_render_resource_path(value)


def _validate_document_variables(variables: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "body_folio_start" in variables:
        value = variables["body_folio_start"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append("variables.body_folio_start must be a positive integer")
    if "colophon_words" in variables:
        value = variables["colophon_words"]
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            errors.append("variables.colophon_words must be an integer or an English phrase")
        elif isinstance(value, int) and value < 1:
            errors.append("variables.colophon_words must be positive")
        elif isinstance(value, str) and not value.strip():
            errors.append("variables.colophon_words must not be empty")
    return errors


def _reserved_document_variable_ingress_errors(
    mapping: dict[str, Any], scope: str
) -> list[str]:
    errors: list[str] = []
    if "body_folio_start" in mapping:
        errors.append(
            f"{scope}.body_folio_start is reserved; set it through "
            "manifest.variables.body_folio_start"
        )
    nested = mapping.get("variables")
    if isinstance(nested, dict) and "body_folio_start" in nested:
        errors.append(
            f"{scope}.variables.body_folio_start is reserved; set it through "
            "manifest.variables.body_folio_start"
        )
    return errors


def _strip_reserved_document_variables(mapping: dict[str, Any]) -> dict[str, Any]:
    """Defense in depth: reserved template variables have one validated ingress."""
    cleaned = dict(mapping)
    cleaned.pop("body_folio_start", None)
    nested = cleaned.get("variables")
    if isinstance(nested, dict):
        cleaned_nested = dict(nested)
        cleaned_nested.pop("body_folio_start", None)
        cleaned["variables"] = cleaned_nested
    return cleaned


def _guard_manifest_variables(variables: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    accepted: dict[str, Any] = {}
    rejected: dict[str, str] = {}
    for key, value in variables.items():
        if key not in DOCUMENT_VARIABLE_ALLOWLIST:
            rejected[key] = "variable key is not allowlisted for document manifests"
            continue
        if key == "body_folio_start" and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            rejected[key] = "body_folio_start must be a positive integer"
            continue
        if not _safe_scalar(value):
            rejected[key] = "variable value must be a scalar"
            continue
        if key in RESOURCE_PATH_VARIABLES and not _safe_render_resource_path(value):
            rejected[key] = f"{key} must be a relative image/PDF path inside the render resource roots"
            continue
        if isinstance(value, str) and not _safe_template_string(value):
            rejected[key] = "variable value contains disallowed LaTeX control tokens"
            continue
        accepted[key] = value
    return accepted, rejected


def _frontmatter_to_markdown(frontmatter: dict[str, Any], body: str) -> str:
    try:
        import yaml as _yaml
        fm_yaml = _yaml.safe_dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False).rstrip()
    except ImportError:
        fm_yaml = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
    separator = "" if body.startswith("\n") else "\n"
    return f"---\n{fm_yaml}\n---{separator}{body}"


SUPPORTED_DIVIDER_STOCKS = {"text", "cardstock", "specialty"}

DOCUMENT_MATTER_ROLE_ALIASES = {
    "document_source": "document_source",
    "document": "document_source",
    "body": "document_source",
    "mainmatter": "document_source",
    "main_matter": "document_source",
    "frontmatter": "frontmatter",
    "front_matter": "frontmatter",
}
DOCUMENT_MATTER_SOURCE_KEYS = ("role", "document_role", "matter")
DOCUMENT_MATTER_FRONTMATTER_KEYS = ("document_role", "render_role", "matter", "role")


def _normalize_document_matter_role(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower().replace("-", "_")
    return DOCUMENT_MATTER_ROLE_ALIASES.get(key)


def _resolve_document_matter_role(
    values: dict[str, Any],
    keys: tuple[str, ...],
    scope: str,
    ignore_unknown_keys: tuple[str, ...] = (),
) -> str | None:
    normalized: list[tuple[str, str]] = []
    for key in keys:
        value = values.get(key)
        if value is None or value == "":
            continue
        role = _normalize_document_matter_role(value)
        if role is None:
            if key in ignore_unknown_keys:
                continue
            raise ValueError(f"{scope}.{key} must be document_source/mainmatter or frontmatter")
        normalized.append((key, role))
    roles = {role for _key, role in normalized}
    if len(roles) > 1:
        details = ", ".join(f"{key}={role}" for key, role in normalized)
        raise ValueError(f"conflicting {scope} matter roles: {details}")
    return normalized[0][1] if normalized else None


def _document_matter_role(source_cfg: dict[str, Any], source_fm: dict[str, Any]) -> str:
    """Return the document/memoir matter role for a single-document render.

    Manifest source config is authoritative; source frontmatter is a weaker hint
    used by the direct document path and by document manifests that do not set a
    source role. Bundle-family renders use their ordered source roles instead.
    """
    source_role = _resolve_document_matter_role(source_cfg, DOCUMENT_MATTER_SOURCE_KEYS, "source")
    if source_role:
        return source_role
    frontmatter_role = _resolve_document_matter_role(
        source_fm,
        DOCUMENT_MATTER_FRONTMATTER_KEYS,
        "source_frontmatter",
        ignore_unknown_keys=("role",),
    )
    return frontmatter_role or "document_source"


def _inject_document_matter_command(body: str, matter_role: str) -> str:
    if matter_role == "frontmatter":
        return "\\frontmatter\n\n" + body.lstrip("\n")
    return body


def _latex_escape_text(value: Any) -> str:
    """Escape scalar text for raw LaTeX divider blocks."""
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _normalized_running_text(owner: dict[str, Any]) -> dict[str, str]:
    raw = owner.get("running_text") or owner.get("header_footer")
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        canonical = RUNNING_TEXT_KEY_ALIASES.get(str(key))
        if canonical is None:
            continue
        normalized[canonical] = "" if value is None else str(value)
    return normalized


def _running_text_override_lines(owner: dict[str, Any]) -> list[str]:
    running_text = _normalized_running_text(owner)
    commands = {
        "division": "OFSetRunningDivision",
        "tagline": "OFSetRunningTagline",
        "footeremail": "OFSetRunningFooter",
    }
    return [
        f"\\{commands[key]}{{{_latex_escape_text(running_text[key])}}}"
        for key in RUNNING_TEXT_CANONICAL_ORDER
        if key in running_text
    ]


def _running_text_inventory_entry(uid: Any, owner: dict[str, Any]) -> dict[str, Any] | None:
    running_text = _normalized_running_text(owner)
    if not running_text:
        return None
    return {"uid": str(uid), "running_text": running_text}


def _validate_running_text(owner: dict[str, Any], scope: str) -> list[str]:
    raw = owner.get("running_text") or owner.get("header_footer")
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"{scope} running_text must be a mapping"]
    errors: list[str] = []
    for key, value in raw.items():
        key_str = str(key)
        if key_str not in RUNNING_TEXT_KEY_ALIASES:
            errors.append(f"{scope} running_text.{key_str} is not a supported key")
            continue
        if value is not None and not isinstance(value, (str, int, float, bool)):
            errors.append(f"{scope} running_text.{key_str} must be a scalar string")
            continue
        if isinstance(value, str) and not _safe_template_string(value):
            errors.append(f"{scope} running_text.{key_str} contains unsafe LaTeX control text")
    return errors


def _source_order_lookup(sources: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    by_uid: dict[str, dict[str, Any]] = {}
    by_order: dict[int, dict[str, Any]] = {}
    for src in sources:
        uid = src.get("uid")
        order = src.get("order")
        if uid:
            by_uid[str(uid)] = src
        if isinstance(order, int):
            by_order[order] = src
    return by_uid, by_order


def _resolved_section_divider_target(
    divider: dict[str, Any],
    sources_by_uid: dict[str, dict[str, Any]],
    sources_by_order: dict[int, dict[str, Any]],
) -> tuple[str, int]:
    before_uid = divider.get("before_source_uid")
    before_order = divider.get("before_source_order")
    if before_uid:
        target = sources_by_uid.get(str(before_uid), {})
        return str(before_uid), int(target.get("order", 0) or 0)
    if isinstance(before_order, int):
        target = sources_by_order.get(before_order, {})
        return str(target.get("uid", "")), before_order
    return "", 0


def _section_divider_profile_fields(divider: dict[str, Any]) -> dict[str, Any]:
    """Resolve optional divider-local profile hints into evidence fields."""
    requested_profile_id = divider.get("profile_id") or divider.get("profile")
    requested_profile_family = divider.get("profile_family")
    if not requested_profile_id and not requested_profile_family:
        return {}
    profile_id = str(requested_profile_id or "document-spine")
    resolved = resolve_profile(profile_id)
    return {
        "requested_profile_id": requested_profile_id,
        "requested_profile_family": requested_profile_family,
        "resolved_profile_id": resolved.canonical_profile_id,
        "resolved_profile_request_id": resolved.profile_id,
        "profile_family": resolved.profile_family,
        "defaults_stack": [path.name for path in resolved.defaults_stack],
        "template": resolved.template_path.name,
    }


def _section_divider_inventory_entry(
    divider: dict[str, Any],
    sources_by_uid: dict[str, dict[str, Any]],
    sources_by_order: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    before_uid, before_order = _resolved_section_divider_target(divider, sources_by_uid, sources_by_order)
    source_cfg = divider.get("source") if isinstance(divider.get("source"), dict) else None
    stock = str(divider.get("stock", "") or "").strip().lower() or "text"
    if stock not in SUPPORTED_DIVIDER_STOCKS:
        stock = "text"
    entry = {
        "uid": divider.get("uid", ""),
        "before_source_uid": before_uid,
        "before_source_order": before_order,
        "kind": "source" if source_cfg else "generic",
        "force_right_page": divider.get("force_right_page", True) is not False,
        "blank_after": divider.get("blank_after", False) is True,
        "background_image": str(divider.get("background_image", "") or ""),
        "stock": stock,
        "print_image": str(divider.get("print_image", "") or ""),
    }
    entry.update(_section_divider_profile_fields(divider))
    running_text_entry = _running_text_inventory_entry(divider.get("uid", ""), divider)
    if running_text_entry:
        entry["running_text"] = running_text_entry["running_text"]
    if source_cfg:
        entry["source_path"] = str(source_cfg.get("path", ""))
    return entry


def _section_divider_start_lines(divider: dict[str, Any]) -> list[str]:
    lines = ["\\OFEnsureRightPage" if divider.get("force_right_page", True) is not False else "\\clearpage"]
    # Compile-stage furnish marker. engine/furnish.py extracts
    # `[[OFDIV:<uid>]]` from the unsanitized renderer intermediate to know which
    # PDF page each divider lands on; the renderer preserves that map as a
    # sidecar, then removes marker text-show operators from the final PDF.
    uid = str(divider.get("uid", "") or "").strip()
    if uid:
        # Invisible compile-stage furnish marker. engine/furnish.py extracts
        # `[[OFDIV:<uid>]]` before final-PDF sanitization; the preserved sidecar
        # then drives imposition/furnish after this token leaves the text layer.
        # `{...}` because pandoc's raw_tex extension strips the outer literal
        # braces when reading the line as raw LaTeX, which would leak
        # \fontsize{1}{1} into the rest of the document. \detokenize{} keeps
        # underscores + other TeX-special chars in the uid from tripping text
        # mode ("Missing $ inserted").
        # Bracketed by \OFDivMarkerHideBegin/End so templates suppress its ink
        # (PDF text render mode 3). It remains extractable in the compile-stage
        # PDF, then the renderer removes its text-show operator from the final
        # PDF after writing the out-of-band divider-page map. This matters because
        # divider pages are no longer always full-bleed artwork: codex0 v5 poem
        # versos are white, where 1pt type prints as a visible hairline across
        # the poem's first line.
        #
        # Two arg-less commands rather than one \OFDivMarkerHide{...} wrapper:
        # pandoc's raw_tex reader STRIPS an unknown macro that takes a braced
        # argument and keeps only the argument, so a wrapper silently no-ops
        # (verified — the emitted .tex came out unwrapped). Bare control
        # sequences survive, as \OFEnsureRightPage above already relies on. The
        # render-mode primitive itself can't be emitted here at all: pandoc
        # mangles its space-separated keyword (`literal{3 Tr}` -> `literal\{`).
        # Emitted inside an explicit ```{=latex} fence so pandoc passes the line
        # through verbatim as a RawBlock. Without the fence pandoc parses this as
        # a paragraph of raw INLINES and silently drops control sequences it
        # doesn't know — both a \cmd{...} wrapper and bare \cmd tokens vanished
        # from the emitted .tex, leaving the marker visible. (Neighbouring lines
        # like \OFEnsureRightPage survive only because each is a standalone
        # block.) The fence also means the Hide macros reach LaTeX intact.
        lines.append("```{=latex}")
        lines.append(
            f"\\begingroup\\fontsize{{1}}{{1}}\\selectfont\\OFDivMarkerHideBegin"
            f"\\hbox{{\\detokenize{{[[OFDIV:{uid}]]}}}}\\OFDivMarkerHideEnd\\endgroup"
        )
        lines.append("```")
    background_image = divider.get("background_image")
    if background_image:
        lines.append(f"\\OFSectionDividerBackground{{{background_image}}}")
    profile = _section_divider_profile_fields(divider)
    if profile:
        lines.append(
            f"\\OFApplySectionDividerProfile{{{profile.get('resolved_profile_id', '')}}}{{{profile.get('profile_family', '')}}}"
        )
    lines.extend(_running_text_override_lines(divider))
    return lines


def _section_divider_end_lines(divider: dict[str, Any]) -> list[str]:
    lines = ["\\clearpage"]
    if divider.get("blank_after", False) is True:
        lines.append("\\OFIntentionalBlankPage")
    return lines


def _centered_numbered_divider_heading(title: str) -> list[str]:
    """Emit section-counter/TOC plumbing plus a divider-safe visible heading.

    Callers place these lines inside an explicit LaTeX center environment. We avoid Pandoc's
    normal `\\section{...}` because the CAM template left-aligns normal body sections, while
    divider pages need centered threshold titles.
    """
    escaped = _latex_escape_text(title)
    return [
        "\\refstepcounter{section}",
        f"\\addcontentsline{{toc}}{{section}}{{\\protect\\numberline{{\\thesection}}{escaped}}}",
        f"\\markright{{{escaped}}}",
        f"{{\\Huge\\bfseries \\thesection\\quad {escaped}\\par}}",
    ]


def _extract_leading_markdown_h1(body: str) -> tuple[str | None, str]:
    """Return the first leading H1 title and body with that heading removed."""
    stripped = body.lstrip()
    match = re.match(r"^#(?!#)\s+(.+?)\s*$", stripped, flags=re.MULTILINE)
    if not match or match.start() != 0:
        return None, body
    title = match.group(1).strip()
    remainder = stripped[match.end():].lstrip("\n")
    return title, remainder


def _render_source_divider(source_cfg: dict[str, Any], divider: dict[str, Any], numbering_strategy: str = "continuous") -> list[str]:
    path = Path(source_cfg["path"])
    raw_text = path.read_text()
    fm, body = _split_frontmatter_and_body(raw_text)
    include_frontmatter = source_cfg.get("include_frontmatter", "none")
    lines = _section_divider_start_lines(divider)
    if include_frontmatter == "full" and fm:
        try:
            import yaml as _yaml
            fm_yaml = _yaml.dump(fm, default_flow_style=False, allow_unicode=True)
        except ImportError:
            fm_yaml = str(fm)
        lines.extend(["\\textbf{Divider Source Frontmatter}", "", "```yaml", fm_yaml.rstrip(), "```", ""])
    elif include_frontmatter == "summary" and fm:
        lines.extend(["\\textbf{Divider Source Frontmatter (summary)}", ""])
        for k, v in sorted(fm.items()):
            if isinstance(v, (list, dict)):
                continue
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    rendered_body = body.strip()
    if numbering_strategy == "section_dividers":
        heading_title, remainder = _extract_leading_markdown_h1(rendered_body)
        if heading_title:
            lines.append("\\begin{center}")
            lines.extend(_centered_numbered_divider_heading(heading_title))
            lines.append("\\end{center}")
            rendered_body = remainder.strip()
    lines.extend([rendered_body, "", *_section_divider_end_lines(divider)])
    return lines


def _render_generic_section_divider(divider: dict[str, Any], numbering_strategy: str = "continuous") -> list[str]:
    title = _latex_escape_text(divider.get("title") or divider.get("uid") or "Section")
    subtitle = _latex_escape_text(divider.get("subtitle", ""))
    body = _latex_escape_text(divider.get("body", ""))
    lines = [
        *_section_divider_start_lines(divider),
        "\\thispagestyle{empty}",
        "\\vspace*{0.30\\textheight}",
        "\\begin{center}",
    ]
    if numbering_strategy == "section_dividers":
        lines.extend(_centered_numbered_divider_heading(title))
    else:
        lines.append(f"{{\\Huge\\bfseries {title}\\par}}")
    if subtitle:
        lines.extend(["\\vspace{0.85em}", f"{{\\Large {subtitle}\\par}}"])
    if body:
        lines.extend(["\\vspace{1.5em}", f"{{\\normalsize {body}\\par}}"])
    lines.extend(["\\end{center}", *_section_divider_end_lines(divider)])
    return lines


def _render_section_divider(divider: dict[str, Any], numbering_strategy: str = "continuous") -> list[str]:
    source_cfg = divider.get("source")
    if isinstance(source_cfg, dict):
        return _render_source_divider(source_cfg, divider, numbering_strategy=numbering_strategy)
    return _render_generic_section_divider(divider, numbering_strategy=numbering_strategy)


_CHAPTER_OPENER_FALLBACK_DEFS = [
    # No-op compatibility fallbacks for profiles without tagged marker macros.
    # They allow compilation to reach evidence generation, where final-PDF
    # sanitization fails closed rather than publishing a visible/unsanitized
    # `[[OFDIV:...]]` token. Tagged templates define the real wrappers first.
    "\\providecommand{\\OFDivMarkerHideBegin}{}",
    "\\providecommand{\\OFDivMarkerHideEnd}{}",
    "\\providecommand{\\OFChapterOpener}[1]{{\\par\\bigskip\\begingroup\\centering\\Large #1\\par\\endgroup\\medskip}}",
    "\\providecommand{\\OFChapterOpenerEpigraph}[2]{{\\par\\bigskip\\begingroup\\centering\\Large #1\\par\\smallskip\\small\\itshape #2\\par\\endgroup\\medskip}}",
    # Fallbacks so a non-codex0 profile can still render a codex-quote epigraph
    # beneath the opener heading. codex0 defines richer versions; these only
    # apply if the profile left them undefined. The attribution fallback mirrors
    # codex0's empty-author handling (emdash+author when author present, else
    # italic source), so source/date survive even without an author.
    "\\providecommand{\\CodexQuoteAttribution}[3]{{\\par\\smallskip{\\raggedleft\\small"
    "\\if\\relax\\detokenize{#1}\\relax\\if\\relax\\detokenize{#2}\\relax\\else\\emph{#2}\\fi"
    "\\else\\textemdash{} #1\\if\\relax\\detokenize{#2}\\relax\\else, \\emph{#2}\\fi\\fi"
    "\\if\\relax\\detokenize{#3}\\relax\\else\\ (#3)\\fi\\par}}}",
    "\\ifdefined\\CodexQuoteBlock\\else\\newenvironment{CodexQuoteBlock}[3]{\\par\\medskip\\begin{quote}\\itshape}{\\end{quote}\\par\\medskip}\\fi",
    # Layered chapter-opener epigraph (2026-07-28 grammar). codex0 defines the
    # rich version (small-caps speaker line, middot bibliographic line, gold
    # context line, register-inverted body); this fallback keeps any other
    # profile safe with a best-effort italic body + em-dash attribution.
    # Args: {register}{text}{speaker}{context}{author}{source}{date}
    "\\providecommand{\\CodexSmallCaps}[1]{\\textsc{#1}}",
    "\\providecommand{\\CodexOpenerEpigraph}[7]{{\\par\\smallskip"
    "\\begin{quote}\\itshape #2\\end{quote}"
    "{\\raggedleft"
    "\\if\\relax\\detokenize{#3}\\relax\\else{\\small\\textemdash{}~\\textsc{#3}"
    "\\if\\relax\\detokenize{#4}\\relax\\else, #4\\fi\\par}\\fi"
    "{\\footnotesize"
    "\\if\\relax\\detokenize{#3}\\relax\\textemdash{}~\\fi"
    "\\if\\relax\\detokenize{#5}\\relax\\else#5\\fi"
    "\\if\\relax\\detokenize{#6}\\relax\\else\\space\\textperiodcentered\\space\\emph{#6}\\fi"
    "\\if\\relax\\detokenize{#7}\\relax\\else\\space\\textperiodcentered\\space#7\\fi\\par}"
    "\\par}}}",
]


def _inline_chapter_opener_epigraph_lines(epigraph: dict[str, Any]) -> list[str]:
    """Lower a structured opener epigraph through the layered attribution grammar.

    The epigraph line is pulled from the corpus (one per chapter) and rendered
    via `\\CodexOpenerEpigraph{register}{text}{speaker}{context}{author}{source}
    {date}` (ratified 2026-07-28). The macro handles the register-inverted quote
    body (witness upright / literary italic), the small-caps speaker line, the
    middot bibliographic line, and the gold context line. The generic
    `CodexQuoteBlock` / `\\CodexQuoteAttribution` grammar is left untouched for
    body-prose fenced `.codex-quote` divs.
    """
    text = str(epigraph.get("text") or "").strip()
    if not text:
        return []

    def esc(key: str) -> str:
        return _latex_escape_text(str(epigraph.get(key) or "").strip())

    register = str(epigraph.get("register") or "").strip().lower()
    # Only an explicit "witness" register inverts the body to upright; anything
    # else (including a missing register) renders literary/italic by default.
    register_arg = "witness" if register == "witness" else "literary"
    speaker = esc("speaker")
    context = esc("context")
    author = esc("author")
    source = esc("source")
    date = esc("date")
    body = _latex_escape_text(text)
    return [
        f"\\CodexOpenerEpigraph{{{register_arg}}}{{{body}}}{{{speaker}}}"
        f"{{{context}}}{{{author}}}{{{source}}}{{{date}}}"
    ]


def _inline_chapter_opener_lines(opener: dict[str, Any]) -> list[str]:
    """Render a chapter's inline opener at the top of its first passage page.

    Replaces the former full-page chapter divider (Item 9, 2026-07-06). Emits a
    visible heading (and optional epigraph) plus TOC / running-header plumbing,
    but no page break of its own — the first passage's own `\\newpage` already
    opens the chapter on a fresh page, so the opener simply headlines it.

    The epigraph may be a mapping (`{text, speaker?, context?, author?, source?,
    date?, register?}`, rendered via the layered `\\CodexOpenerEpigraph` grammar
    beneath the heading) or a plain string (rendered via the profile-styled
    `\\OFChapterOpenerEpigraph` macro). The
    `\\OFChapterOpener` macros are profile-styled (codex0 overrides them); the
    fallback definitions emitted once upstream keep any profile safe.
    """
    title = str(opener.get("title") or "").strip()
    if not title:
        return []
    escaped = _latex_escape_text(title)
    lines = [
        "\\phantomsection",
        # Registered one level below the part dividers' section-level entries so
        # a TOC can show parts alone via tocdepth=1 (chapters reappear at >=2).
        f"\\addcontentsline{{toc}}{{subsection}}{{{escaped}}}",
        f"\\markboth{{{escaped}}}{{{escaped}}}",
    ]
    epigraph = opener.get("epigraph")
    if isinstance(epigraph, dict):
        lines.append(f"\\OFChapterOpener{{{escaped}}}")
        lines.extend(_inline_chapter_opener_epigraph_lines(epigraph))
    elif isinstance(epigraph, str) and epigraph.strip():
        lines.append(f"\\OFChapterOpenerEpigraph{{{escaped}}}{{{_latex_escape_text(epigraph.strip())}}}")
    else:
        lines.append(f"\\OFChapterOpener{{{escaped}}}")
    return lines


def _title_page_variables_from_presentation(presentation: dict[str, Any]) -> dict[str, Any]:
    """Return canonical Pandoc variables for a bundle title-page surface."""
    title_page = presentation.get("title_page", {}) if isinstance(presentation, dict) else {}
    if not isinstance(title_page, dict):
        return {}

    variables: dict[str, Any] = {}
    enabled = title_page.get("enabled")
    background_image = title_page.get("background_image")
    blank_after = title_page.get("blank_after", True)

    if enabled is True or background_image:
        variables["titlepage"] = True
    if background_image and enabled is not False:
        variables["titlepage_background_image"] = background_image
    if blank_after is not False and (enabled is True or background_image):
        variables["titlepage_blank_after"] = True
    return variables


class MarkdownDocumentCompiler(ManifestCompiler):
    """Compile markdown_document / document_manifest_v1.

    This is the faithful single-document manifest lane. It preserves the source
    Markdown body and routes the document through the same profile/render path as
    a direct document render while allowing manifest-visible metadata overrides,
    render controls, and guarded profile/template variables.
    """

    kind = "markdown_document"
    schema_version = "document_manifest_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        source_cfg = manifest.get("source", {})
        source_path = Path(source_cfg["path"])
        profile = manifest["profile"]
        render_cfg = manifest.get("render", {}) if isinstance(manifest.get("render", {}), dict) else {}
        metadata = manifest.get("metadata", {}) if isinstance(manifest.get("metadata", {}), dict) else {}
        variables = manifest.get("variables", {}) if isinstance(manifest.get("variables", {}), dict) else {}

        raw_text = source_path.read_text()
        source_fm, body = _split_frontmatter_and_body(raw_text)
        source_fm = source_fm or {}

        preserve_source_metadata = render_cfg.get("preserve_source_metadata", True)
        merge_policy = render_cfg.get("metadata_merge_policy", "source_then_manifest_override")
        if merge_policy != "source_then_manifest_override":
            raise ValueError(f"unsupported metadata_merge_policy: {merge_policy}")

        accepted_variables, rejected_variables = _guard_manifest_variables(variables)
        merged_fm: dict[str, Any] = dict(source_fm) if preserve_source_metadata else {}
        merged_fm.update(metadata)
        # `body_folio_start` is directly lowered into a TeX integer context. Its
        # sole supported ingress is the validated top-level manifest.variables
        # mapping; strip source/metadata copies defensively even though validate()
        # rejects them before normal compilation.
        merged_fm = _strip_reserved_document_variables(merged_fm)
        if accepted_variables:
            existing_vars = merged_fm.get("variables", {}) if isinstance(merged_fm.get("variables", {}), dict) else {}
            merged_fm["variables"] = {**existing_vars, **accepted_variables}
            # Also expose common Pandoc template variables at top level because
            # imported 40_latex defaults/templates expect scalar variables there.
            for key, value in accepted_variables.items():
                merged_fm[key] = value

        title = metadata.get("title", merged_fm.get("title", source_path.stem))
        subtitle = metadata.get("subtitle", merged_fm.get("subtitle", ""))
        author = metadata.get("author", merged_fm.get("author", ""))
        date = metadata.get("date", merged_fm.get("date", ""))
        toc = bool(render_cfg["include_toc"]) if "include_toc" in render_cfg else bool(merged_fm.get("toc", True))
        toc_depth = int(render_cfg.get("toc_depth", merged_fm.get("toc-depth", 3)))
        numbersections = bool(render_cfg["numbersections"]) if "numbersections" in render_cfg else bool(merged_fm.get("numbersections", True))
        page_size, page_size_source = page_size_from_mapping(render_cfg, scope="manifest.render")
        if page_size_source == "default" and preserve_source_metadata:
            page_size, page_size_source = page_size_from_mapping(source_fm, scope="source_frontmatter")
        if page_size_source == "default":
            page_size, page_size_source = _profile_default_page_size_for(profile)
        page_margins, page_margins_source = page_margins_from_mapping(render_cfg, scope="manifest.render")
        if page_margins_source == "default" and preserve_source_metadata:
            page_margins, page_margins_source = page_margins_from_mapping(source_fm, scope="source_frontmatter")
        delivery = normalize_delivery(render_cfg, scope="render.delivery")
        if page_margins_source == "default" and delivery.get("mode") == "bound":
            page_margins = delivery_page_margins(delivery)
            page_margins_source = "manifest.render.delivery"
        matter_role = _document_matter_role(source_cfg, source_fm)

        render_id = manifest.get("document_id") or manifest.get("render_id") or merged_fm.get("uid") or source_path.stem
        compiled_body = _inject_document_matter_command(body, matter_role)
        delivery_pagination_overrides = {
            "policy": "none",
            "enlargethispage_suppressed": 0,
            "commands_suppressed": [],
        }
        delivery_running_header_marks = {
            "enabled": False,
            "source": "chapter",
            "marks_inserted": 0,
        }
        delivery_illumination_marks = {
            "enabled": False,
            "placement": "",
            "marks_inserted": 0,
            "assets_used": [],
        }
        if delivery.get("mode") == "bound":
            compiled_body, delivery_pagination_overrides = suppress_bound_pagination_overrides(compiled_body)
            illumination = delivery.get("illumination", {}) if isinstance(delivery.get("illumination"), dict) else {}
            if illumination.get("enabled"):
                compiled_body, delivery_illumination_marks = inject_bound_illumination_rail_marks(compiled_body, illumination)
            running_headers = delivery.get("running_headers", {}) if isinstance(delivery.get("running_headers"), dict) else {}
            if running_headers.get("enabled"):
                compiled_body, delivery_running_header_marks = inject_bound_running_header_marks(
                    compiled_body,
                    source=str(running_headers.get("source", "chapter")),
                )
        delivery_colophon_emitted = False
        colophon = delivery.get("colophon", {}) if isinstance(delivery.get("colophon"), dict) else {}
        if delivery.get("mode") == "bound" and colophon.get("enabled") and colophon.get("placement") == "title_verso":
            compiled_body, delivery_colophon_emitted = insert_title_verso_colophon(
                compiled_body,
                bound_colophon_block(
                    title=str(title) if title is not None else "",
                    author=str(author) if author is not None else "",
                    date=str(date) if date is not None else "",
                    render_id=str(render_id),
                    delivery=delivery,
                ),
            )
        compiled_text = _frontmatter_to_markdown(merged_fm, compiled_body)
        render_source = _write_temp_markdown(f"document_{render_id}", compiled_text)

        source_digest = _sha256_hex(source_path)
        boundary_assertions = {
            "target_legacy_profile_tree_mutated": False,
            "profile_manifest_axes_separate": True,
            "document_manifest_lane": True,
            "manifest_family": "document",
            "manifest_subtype": self.kind,
            "assembly_strategy": "direct_markdown",
            "metadata_merge_policy": merge_policy,
            "preserve_source_metadata": preserve_source_metadata,
            "heading_transform": render_cfg.get("heading_transform", source_cfg.get("heading_transform", "preserve")),
            "emit_visible_provenance": render_cfg.get("emit_visible_provenance", False),
            "preserve_source_provenance": render_cfg.get("preserve_source_provenance", True),
            "document_matter_role": matter_role,
            "frontmatter_mode_enabled": matter_role == "frontmatter",
            "page_size": page_size,
            "page_size_source": page_size_source,
            "page_margins": page_margins,
            "page_margins_source": page_margins_source,
            "delivery_colophon_emitted": delivery_colophon_emitted,
            "delivery_pagination_overrides": delivery_pagination_overrides,
            "delivery_running_header_marks": delivery_running_header_marks,
            "delivery_illumination_marks": delivery_illumination_marks,
            **delivery_boundary(delivery),
            "accepted_manifest_variables": sorted(accepted_variables.keys()),
            "rejected_manifest_variables": rejected_variables,
        }
        if rejected_variables:
            boundary_assertions["warnings"] = [
                f"Rejected document manifest variable {key}: {reason}"
                for key, reason in sorted(rejected_variables.items())
            ]

        return ProjectionPlan(
            profile_id=profile,
            render_id=str(render_id),
            render_source=render_source,
            title=str(title) if title is not None else "",
            subtitle=str(subtitle) if subtitle is not None else "",
            author=str(author) if author is not None else "",
            date=str(date) if date is not None else "",
            toc=toc,
            toc_depth=toc_depth,
            numbersections=numbersections,
            page_size=page_size,
            page_margins=page_margins,
            delivery=delivery,
            source_inventory=[
                {
                    "uid": str(render_id),
                    "path": str(source_path),
                    "role": matter_role,
                    "digest_sha256": source_digest,
                    "manifest_lane": self.kind,
                }
            ],
            source_resource_roots=[source_path.parent],
            boundary_assertions=boundary_assertions,
        )

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]
        if manifest.get("kind") != self.kind:
            errors.append(f"expected kind={self.kind}, got {manifest.get('kind')}")
        if manifest.get("schema_version") != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {manifest.get('schema_version')}")
        if not manifest.get("profile"):
            errors.append("missing profile")
        source = manifest.get("source")
        if not isinstance(source, dict):
            errors.append("source must be a mapping with path")
        else:
            path = source.get("path")
            if not path:
                errors.append("source.path is required")
            elif not Path(path).exists():
                errors.append(f"source.path not found: {path}")
            else:
                source_fm, _source_body = _split_frontmatter_and_body(Path(path).read_text(errors="ignore"))
                if source_fm:
                    errors.extend(
                        _reserved_document_variable_ingress_errors(
                            source_fm, "source_frontmatter"
                        )
                    )
                    try:
                        _resolve_document_matter_role(
                            source_fm,
                            DOCUMENT_MATTER_FRONTMATTER_KEYS,
                            "source_frontmatter",
                            ignore_unknown_keys=("role",),
                        )
                    except ValueError as exc:
                        errors.append(str(exc))
            try:
                _resolve_document_matter_role(source, DOCUMENT_MATTER_SOURCE_KEYS, "source")
            except ValueError as exc:
                errors.append(str(exc))
        metadata = manifest.get("metadata", {})
        if metadata is not None and not isinstance(metadata, dict):
            errors.append("metadata must be a mapping")
        elif isinstance(metadata, dict):
            errors.extend(
                _reserved_document_variable_ingress_errors(metadata, "metadata")
            )
        render_cfg = manifest.get("render", {})
        if render_cfg is not None and not isinstance(render_cfg, dict):
            errors.append("render must be a mapping")
        elif isinstance(render_cfg, dict):
            try:
                page_size_from_mapping(render_cfg, scope="render")
            except PageSizeError as exc:
                errors.append(str(exc))
            try:
                page_margins_from_mapping(render_cfg, scope="render")
            except PageMarginError as exc:
                errors.append(str(exc))
            errors.extend(validate_delivery(render_cfg, scope="render.delivery"))
        variables = manifest.get("variables", {})
        if variables is not None and not isinstance(variables, dict):
            errors.append("variables must be a mapping")
        elif isinstance(variables, dict):
            errors.extend(_validate_document_variables(variables))
        return errors


class CompositeBundleCompiler(ManifestCompiler):
    """Compile a composite_bundle / bundle_manifest_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    containing a title page, reader guide, TOC, ordered source sections (with
    frontmatter blocks), figures, afterword, and provenance block.
    """

    kind = "composite_bundle"
    schema_version = "bundle_manifest_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        bundle_id = manifest["bundle_id"]
        profile = manifest["profile"]
        pres = manifest.get("presentation", {})
        title = pres.get("title", manifest.get("bundle_name", bundle_id))
        subtitle = pres.get("subtitle", "")
        authors = pres.get("authors", [])
        date = pres.get("date", "")

        render_cfg = manifest.get("render", {})
        page_size, page_size_source = page_size_from_mapping(render_cfg if isinstance(render_cfg, dict) else {}, scope="manifest.render")
        if page_size_source == "default":
            page_size, page_size_source = _profile_default_page_size_for(profile)
        page_margins, page_margins_source = page_margins_from_mapping(
            render_cfg if isinstance(render_cfg, dict) else {}, scope="manifest.render"
        )
        # Delivery-based margin fallback: mirrors MarkdownDocumentCompiler so
        # a bundle manifest can express book margins via render.delivery.margins
        # (the standard bound-delivery inner/outer/top/bottom surface) instead
        # of duplicating them at render.margins. Only fires when render.margins
        # was not set explicitly and delivery is bound.
        _bundle_delivery = normalize_delivery(render_cfg, scope="render.delivery") if isinstance(render_cfg, dict) else {}
        if page_margins_source == "default" and _bundle_delivery.get("mode") == "bound":
            _bundle_delivery_margins = delivery_page_margins(_bundle_delivery)
            if _bundle_delivery_margins:
                page_margins = _bundle_delivery_margins
                page_margins_source = "manifest.render.delivery"
        gen_cfg = manifest.get("generated", {})
        title_page_variables = _title_page_variables_from_presentation(pres)
        accepted_title_page_variables, rejected_title_page_variables = _guard_manifest_variables(title_page_variables)

        # Bundle-level `variables:` (allowlisted). Enables Codex 0 editions
        # (`codex_edition`, `codex_strip_editorial_callouts`) and other document
        # variables to flow through a bundle render the same way they do for
        # markdown_document manifests. Guarded through _guard_manifest_variables
        # so only allowlisted keys reach the assembled intermediate.
        raw_manifest_variables = manifest.get("variables", {}) if isinstance(manifest.get("variables", {}), dict) else {}
        accepted_manifest_variables, rejected_manifest_variables = _guard_manifest_variables(raw_manifest_variables)

        sources = manifest.get("sources", [])
        figures = manifest.get("figures", [])
        section_dividers = manifest.get("section_dividers", [])
        sorted_sources = sorted(sources, key=lambda s: s.get("order", 99))
        sources_by_uid, sources_by_order = _source_order_lookup(sorted_sources)
        dividers_by_before_uid: dict[str, list[dict[str, Any]]] = {}
        section_divider_inventory: list[dict[str, Any]] = []
        source_running_text_inventory: list[dict[str, Any]] = []
        for src in sorted_sources:
            running_text_entry = _running_text_inventory_entry(src.get("uid", ""), src)
            if running_text_entry:
                source_running_text_inventory.append(running_text_entry)
        for divider in section_dividers if isinstance(section_dividers, list) else []:
            before_uid, _before_order = _resolved_section_divider_target(divider, sources_by_uid, sources_by_order)
            if not before_uid:
                continue
            dividers_by_before_uid.setdefault(before_uid, []).append(divider)
            section_divider_inventory.append(_section_divider_inventory_entry(divider, sources_by_uid, sources_by_order))
        assembly_strategy = str(render_cfg.get("assembly_strategy", ""))
        faithful_stack = assembly_strategy == "faithful_stack"
        requested_numbering_strategy = str(render_cfg.get("numbering_strategy") or render_cfg.get("numbering") or "continuous")
        section_divider_numbering = "section_dividers" if requested_numbering_strategy in {
            "section_dividers",
            "faithful_section_dividers",
        } else "continuous"
        suppress_source_wrapper_headings = bool(
            render_cfg.get("suppress_source_wrapper_headings", faithful_stack or section_divider_numbering == "section_dividers")
        )
        preserve_source_heading_levels = bool(
            render_cfg.get("preserve_source_heading_levels", faithful_stack)
        )
        emit_visible_provenance = bool(render_cfg.get("emit_visible_provenance", not faithful_stack))

        # --- build assembly view ---
        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=title,
            assembly_subtitle=subtitle,
            source_order=[],
            source_paths={},
            source_roles={},
            source_digests={},
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        # --- assemble intermediate Markdown ---
        lines: list[str] = []

        # Title metadata is passed through Pandoc --metadata; the template
        # renders the title page from metadata. We add a brief preamble.
        abstract = pres.get("abstract", "")
        if abstract:
            lines.append(f"> {abstract}")
            lines.append("")

        # TOC is handled by PandocRenderer's --toc flag via ProjectionPlan.toc.
        # Do not emit \tableofcontents here (would duplicate pandoc --toc).

        # reader guide
        rg = gen_cfg.get("reader_guide", {})
        if rg.get("enabled", False):
            rg_title = rg.get("title", "Reader Guide")
            lines.append("\\newpage")
            lines.append(f"# {rg_title}")
            for section_line in rg.get("sections", []):
                lines.append(section_line)
                lines.append("")

        # source sections
        source_order_uid = []
        frontmatter_seen = False
        mainmatter_started = False
        appendices_started = False
        if any(isinstance(s.get("chapter_opener"), dict) for s in sorted_sources):
            lines.extend(_CHAPTER_OPENER_FALLBACK_DEFS)
            lines.append("")
        for src in sorted_sources:
            uid = src["uid"]
            src_role = src.get("role", "primary_anchor")
            if src_role == "frontmatter" and not frontmatter_seen:
                lines.append("\\frontmatter")
                frontmatter_seen = True
            elif src_role != "frontmatter" and frontmatter_seen and not mainmatter_started:
                lines.append("\\mainmatter")
                mainmatter_started = True
            if src_role == "appendix" and not appendices_started:
                lines.append("\\OFBeginAppendices")
                appendices_started = True
            source_has_divider = bool(dividers_by_before_uid.get(uid, []))
            for divider in dividers_by_before_uid.get(uid, []):
                lines.extend(_render_section_divider(divider, numbering_strategy=section_divider_numbering))
                lines.append("")
                assembly.generated_sections.append(f"section_divider:{divider.get('uid', '')}")
            src_path = Path(src["path"])
            src_title = src.get("title", uid)
            inc_fm = src.get("include_frontmatter", "full")
            suppress_fm = src.get("suppress_frontmatter", False)

            assembly.source_order.append(uid)
            assembly.source_paths[uid] = str(src_path)
            assembly.source_roles[uid] = src_role

            if not src_path.exists():
                continue

            assembly.source_digests[uid] = _sha256_hex(src_path)

            raw_text = src_path.read_text()
            fm, body = _split_frontmatter_and_body(raw_text)

            # Per-source page break. A source may opt out (page_break_before:
            # false) to flow continuously after the previous source — e.g. a
            # chapter's continuation passages that breathe via a separator
            # ornament instead of each starting a new page (Item 10). When the
            # break is suppressed, emit the requested passage separator unless
            # the body already opens with an authored cx0 ornament marker (the
            # author's explicit marker wins, so we don't double the ornament).
            if src.get("page_break_before", True):
                lines.append("\\newpage")
            else:
                separator = src.get("passage_separator")
                if separator and not _body_opens_with_cx0_marker(body):
                    lines.append(f"<!-- cx0:{separator} -->")
                    lines.append("")
            lines.extend(_running_text_override_lines(src))
            opener_cfg = src.get("chapter_opener")
            if isinstance(opener_cfg, dict):
                opener_lines = _inline_chapter_opener_lines(opener_cfg)
                if opener_lines:
                    lines.extend(opener_lines)
                    lines.append("")
            if not suppress_source_wrapper_headings:
                lines.append(f"# {src_title}")

            # frontmatter block
            if not suppress_fm and inc_fm == "full" and fm:
                try:
                    import yaml as _yaml
                    fm_yaml = _yaml.dump(fm, default_flow_style=False, allow_unicode=True)
                except ImportError:
                    fm_yaml = str(fm)
                lines.append("\\textbf{Source Frontmatter}")
                lines.append("")
                lines.append("```yaml")
                lines.append(fm_yaml.rstrip())
                lines.append("```")
                lines.append("")
            elif not suppress_fm and inc_fm == "summary" and fm:
                lines.append("\\textbf{Source Frontmatter (summary)}")
                lines.append("")
                for k, v in sorted(fm.items()):
                    if isinstance(v, (list, dict)):
                        continue
                    lines.append(f"- **{k}**: {v}")
                lines.append("")

            # source body; default bundle behavior demotes headings below the
            # wrapper heading, while faithful-stack renders preserve source
            # heading hierarchy so canonical longform sources remain intact.
            if section_divider_numbering == "section_dividers" and source_has_divider:
                source_body = _demote_headings(body, levels=1)
            else:
                source_body = body if preserve_source_heading_levels else _demote_headings(body)
            source_register = src.get("codex_register")
            if source_register:
                # Source-register authority wraps only the passage body. Chapter
                # openers, running-text changes, and passage separators were
                # already emitted above and remain outside the semantic field.
                source_body = _wrap_codex_source_register(source_body, str(source_register))
            lines.append(source_body.rstrip())
            lines.append("")

            # figures placed after this source
            src_order = src.get("order", 0)
            for fig in figures:
                if fig.get("after_source_order", -1) == src_order:
                    fig_path = fig.get("path", "")
                    caption = fig.get("caption", "")
                    placement = fig.get("placement", "dedicated_page")
                    if placement == "dedicated_page":
                        lines.append(f"\\newpage")
                    lines.append(f"![]({fig_path})" if not caption else f"![]({fig_path}){{{{width=80%}}}}")
                    if caption:
                        lines.append(f"\\textit{{{caption}}}")
                    lines.append("")

        # afterword
        aw = gen_cfg.get("afterword", {})
        if aw.get("enabled", False):
            aw_title = aw.get("title", "Afterword")
            aw_content = aw.get("content", "")
            lines.append("\\newpage")
            lines.append(f"# {aw_title}")
            if aw_content:
                lines.append(aw_content)
            lines.append("")

        # provenance block
        if emit_visible_provenance:
            lines.append("\\newpage")
            lines.append("# Provenance & Evidence")
            lines.append("\\textbf{Source Inventory}")
            lines.append("")
            for uid in assembly.source_order:
                path = assembly.source_paths.get(uid, "")
                role = assembly.source_roles.get(uid, "")
                digest = assembly.source_digests.get(uid, "(missing)")
                lines.append(f"- **{uid}** ({role}): `{path}` [sha256: `{digest[:16]}...`]")
            if figures:
                lines.append("")
                lines.append("\\textbf{Figure Inventory}")
                lines.append("")
                for fig in figures:
                    lines.append(f"- {fig.get('caption', fig.get('path', 'unknown'))}: `{fig.get('path', '?')}`")

        # Bundle-family title-verso colophon. Emit the colophon fenced-LaTeX
        # block at the very start of the assembled body and, when a TOC is
        # requested, emit `\tableofcontents` immediately after so the running
        # order is: template title → body[colophon → TOC → content]. Pandoc's
        # own --toc (via ProjectionPlan.toc / template `$if(toc)$`) is turned
        # off in that case so the TOC isn't rendered twice. The colophon fills
        # the title verso, so titlepage_blank_after is dropped (an intentional
        # blank there would push the colophon off the verso).
        delivery_colophon_emitted = False
        _delivery_cfg = render_cfg.get("delivery", {}) if isinstance(render_cfg, dict) else {}
        _colophon_cfg = _delivery_cfg.get("colophon", {}) if isinstance(_delivery_cfg.get("colophon"), dict) else {}
        _colophon_active = (
            _delivery_cfg.get("mode") == "bound"
            and _colophon_cfg.get("enabled")
            and _colophon_cfg.get("placement", "title_verso") == "title_verso"
        )
        _bundle_toc_via_body = False
        prelude_lines: list[str] = []
        if _colophon_active:
            prelude_lines.append(bound_colophon_block(
                title=str(title) if title is not None else "",
                author=", ".join(authors) if authors else "",
                date=str(date) if date is not None else "",
                render_id=str(bundle_id),
                delivery=_delivery_cfg,
            ))
            prelude_lines.append("")
            if render_cfg.get("include_toc", True):
                prelude_lines.append("```{=latex}")
                prelude_lines.append("\\tableofcontents")
                prelude_lines.append("\\clearpage")
                prelude_lines.append("```")
                prelude_lines.append("")
                _bundle_toc_via_body = True
            delivery_colophon_emitted = True

        assembled_content = "\n".join(lines)
        if prelude_lines:
            assembled_content = "\n".join(prelude_lines) + "\n" + assembled_content
        # Build-time colophon measure: the codex0 spine tool computes the
        # assembled prose-word count and carries it as the allowlisted
        # `colophon_words` variable; the colophon source leaves a
        # <<COLOPHON_WORDS>> placeholder which is substituted here, after
        # assembly, so the printed number always reflects this exact build.
        colophon_words_value = accepted_manifest_variables.get("colophon_words")
        if colophon_words_value is not None:
            assembled_content = assembled_content.replace(
                "<<COLOPHON_WORDS>>", str(colophon_words_value)
            )
        # Merge title-page variables and bundle-level manifest variables into a
        # single frontmatter block. Both surfaces write to top-level keys AND
        # under `variables:` so downstream readers (edition_from_source_frontmatter,
        # Pandoc template variables) find them regardless of nesting preference.
        merged_frontmatter_variables: dict[str, Any] = {
            **accepted_title_page_variables,
            **accepted_manifest_variables,
        }
        if _colophon_active:
            merged_frontmatter_variables.pop("titlepage_blank_after", None)
        if merged_frontmatter_variables:
            frontmatter = {
                **merged_frontmatter_variables,
                "variables": dict(merged_frontmatter_variables),
            }
            assembled_content = _frontmatter_to_markdown(frontmatter, assembled_content)
        render_source = _write_temp_markdown(f"bundle_{bundle_id}", assembled_content)

        # --- build ProjectionPlan ---
        plan = ProjectionPlan(
            profile_id=profile,
            render_id=bundle_id,
            render_source=render_source,
            title=title,
            subtitle=subtitle,
            author=", ".join(authors),
            date=date,
            toc=(False if _bundle_toc_via_body else render_cfg.get("include_toc", True)),
            toc_depth=render_cfg.get("toc_depth", 3),
            numbersections=render_cfg.get("numbersections", True),
            page_size=page_size,
            page_margins=page_margins,
            delivery=_delivery_cfg,
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "path": assembly.source_paths.get(uid),
                    "role": assembly.source_roles.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            figure_inventory=[
                {"path": f.get("path"), "caption": f.get("caption"), "placement": f.get("placement")}
                for f in figures
            ],
            boundary_assertions={
                **_manifest_boundary_assertions(render_plan),
                "emit_visible_provenance": emit_visible_provenance,
                "suppress_source_wrapper_headings": suppress_source_wrapper_headings,
                "preserve_source_heading_levels": preserve_source_heading_levels,
                "title_page_background_enabled": "titlepage_background_image" in accepted_title_page_variables,
                "titlepage_background_image": accepted_title_page_variables.get("titlepage_background_image", ""),
                "titlepage_blank_after": "titlepage_blank_after" in accepted_title_page_variables,
                "page_size": page_size,
                "page_size_source": page_size_source,
                "page_margins": page_margins,
                "page_margins_source": page_margins_source,
                "accepted_title_page_variables": sorted(accepted_title_page_variables.keys()),
                "rejected_title_page_variables": rejected_title_page_variables,
                "accepted_manifest_variables": sorted(accepted_manifest_variables.keys()),
                "rejected_manifest_variables": rejected_manifest_variables,
                "delivery_colophon_emitted": delivery_colophon_emitted,
                "section_divider_numbering": section_divider_numbering,
                "section_dividers_enabled": bool(section_divider_inventory),
                "section_divider_count": len(section_divider_inventory),
                "section_dividers": section_divider_inventory,
                "source_running_text_overrides": source_running_text_inventory,
            },
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        # envelope
        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("bundle_id"):
            errors.append("missing bundle_id")

        if not manifest.get("profile"):
            errors.append("missing profile")

        render_cfg = manifest.get("render", {})
        if render_cfg is not None and not isinstance(render_cfg, dict):
            errors.append("render must be a mapping")
        elif isinstance(render_cfg, dict):
            try:
                page_size_from_mapping(render_cfg, scope="render")
            except PageSizeError as exc:
                errors.append(str(exc))
            try:
                page_margins_from_mapping(render_cfg, scope="render")
            except PageMarginError as exc:
                errors.append(str(exc))

        variables = manifest.get("variables", {})
        if variables is not None and not isinstance(variables, dict):
            errors.append("variables must be a mapping")
        elif isinstance(variables, dict):
            errors.extend(_validate_document_variables(variables))

        pres = manifest.get("presentation", {})
        if pres is not None and not isinstance(pres, dict):
            errors.append("presentation must be a mapping")
        elif isinstance(pres, dict):
            title_page = pres.get("title_page", {})
            if title_page is not None and not isinstance(title_page, dict):
                errors.append("presentation.title_page must be a mapping")
            elif isinstance(title_page, dict):
                background_image = title_page.get("background_image")
                if background_image and not _safe_render_resource_path(background_image):
                    errors.append(
                        "presentation.title_page.background_image must be a relative PNG/JPG/PDF path inside the render resource roots"
                    )

        # sources
        sources = manifest.get("sources")
        if not sources or not isinstance(sources, list):
            errors.append("sources must be a non-empty list")
        else:
            seen_uids = set()
            seen_orders = set()
            for i, src in enumerate(sources):
                uid = src.get("uid")
                if not uid:
                    errors.append(f"source[{i}] missing uid")
                elif uid in seen_uids:
                    errors.append(f"duplicate uid: {uid}")
                else:
                    seen_uids.add(uid)

                order = src.get("order")
                if order is None or not isinstance(order, int) or order < 1:
                    errors.append(f"source[{i}] missing or invalid order")
                elif order in seen_orders:
                    errors.append(f"duplicate order: {order}")
                else:
                    seen_orders.add(order)

                path = src.get("path")
                if not path:
                    errors.append(f"source[{i}] missing path")
                elif not Path(path).exists():
                    errors.append(f"source[{i}] path not found: {path}")

                role = src.get("role")
                if role not in {"frontmatter", "primary_anchor", "supporting_anchor", "appendix", "reference"}:
                    errors.append(f"source[{i}] unknown role: {role}")
                register = src.get("codex_register")
                if register is not None:
                    scope = f"sources[{i}].codex_register"
                    if self.kind != "codex_bundle":
                        errors.append(f"{scope} is supported only by codex_bundle manifests")
                    elif manifest.get("profile") != "codex0":
                        errors.append(f"{scope} requires profile codex0")
                    elif not isinstance(register, str) or register.strip().lower() not in _SUPPORTED_CODEX_SOURCE_REGISTERS:
                        errors.append(
                            f"{scope} must be one of {sorted(_SUPPORTED_CODEX_SOURCE_REGISTERS)}"
                        )
                errors.extend(_validate_running_text(src, f"source[{i}]"))

        # figures
        figures = manifest.get("figures", [])
        if isinstance(figures, list):
            for i, fig in enumerate(figures):
                if not fig.get("path"):
                    errors.append(f"figure[{i}] missing path")

        # section dividers
        section_dividers = manifest.get("section_dividers", [])
        if section_dividers is None:
            section_dividers = []
        if not isinstance(section_dividers, list):
            errors.append("section_dividers must be a list")
        else:
            sources_for_lookup = manifest.get("sources", []) if isinstance(manifest.get("sources", []), list) else []
            sources_by_uid, sources_by_order = _source_order_lookup(sources_for_lookup)
            seen_divider_uids: set[str] = set()
            for i, divider in enumerate(section_dividers):
                if not isinstance(divider, dict):
                    errors.append(f"section_divider[{i}] must be a mapping")
                    continue

                uid = divider.get("uid")
                if not isinstance(uid, str) or not uid.strip():
                    errors.append(f"section_divider[{i}] missing uid")
                elif uid in seen_divider_uids:
                    errors.append(f"duplicate section_divider uid: {uid}")
                else:
                    seen_divider_uids.add(uid)

                before_uid = divider.get("before_source_uid")
                before_order = divider.get("before_source_order")
                if before_uid is None and before_order is None:
                    errors.append(f"section_divider[{i}] must set before_source_uid or before_source_order")
                if before_uid is not None and str(before_uid) not in sources_by_uid:
                    errors.append(f"section_divider[{i}] before_source_uid not found: {before_uid}")
                if before_order is not None:
                    if not isinstance(before_order, int) or before_order < 1:
                        errors.append(f"section_divider[{i}] before_source_order must be a positive integer")
                    elif before_order not in sources_by_order:
                        errors.append(f"section_divider[{i}] before_source_order not found: {before_order}")

                source_cfg = divider.get("source")
                if source_cfg is not None:
                    if not isinstance(source_cfg, dict):
                        errors.append(f"section_divider[{i}] source must be a mapping")
                    else:
                        source_path = source_cfg.get("path")
                        if not source_path:
                            errors.append(f"section_divider[{i}] source missing path")
                        elif not Path(source_path).exists():
                            errors.append(f"section_divider[{i}] source path not found: {source_path}")
                        include_frontmatter = source_cfg.get("include_frontmatter", "none")
                        if include_frontmatter not in {"full", "summary", "none"}:
                            errors.append(f"section_divider[{i}] source include_frontmatter must be full, summary, or none")
                elif not divider.get("title"):
                    errors.append(f"section_divider[{i}] missing title for generic divider")

                for key in ("title", "subtitle", "body", "profile_id", "profile", "profile_family"):
                    value = divider.get(key)
                    if value is not None and not isinstance(value, str):
                        errors.append(f"section_divider[{i}] {key} must be a string")

                background_image = divider.get("background_image")
                if background_image and not _safe_render_resource_path(background_image):
                    errors.append(
                        f"section_divider[{i}] background_image must be a relative PNG/JPG/PDF path inside the render resource roots"
                    )
                for key in ("force_right_page", "blank_after"):
                    value = divider.get(key)
                    if value is not None and not isinstance(value, bool):
                        errors.append(f"section_divider[{i}] {key} must be a boolean")
                errors.extend(_validate_running_text(divider, f"section_divider[{i}]"))
                requested_profile_id = divider.get("profile_id") or divider.get("profile")
                requested_profile_family = divider.get("profile_family")
                if requested_profile_id or requested_profile_family:
                    try:
                        resolved = resolve_profile(str(requested_profile_id or "document-spine"))
                        if requested_profile_family and resolved.profile_family != requested_profile_family:
                            errors.append(
                                f"section_divider[{i}] requested profile_family={requested_profile_family} "
                                f"but {requested_profile_id or 'document-spine'} resolves to {resolved.profile_family}"
                            )
                    except Exception as exc:
                        errors.append(f"section_divider[{i}] profile resolution failed: {exc}")

        return errors


class CAMStackCompiler(CompositeBundleCompiler):
    """Compile a cam_stack / bundle_manifest_v1 manifest using bundle semantics."""

    kind = "cam_stack"


class CodexBundleCompiler(CompositeBundleCompiler):
    """Compile a codex_bundle / bundle_manifest_v1 manifest using bundle semantics."""

    kind = "codex_bundle"


class LabelRunCompiler(ManifestCompiler):
    """Compile a label_run / label_run_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    with slot-ordered label content, each drawn from its label source file.
    """

    kind = "label_run"
    schema_version = "label_run_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        run_id = manifest["run_id"]
        profile = manifest["profile"]
        sheet_spec = manifest.get("sheet_spec", "")
        output_name = manifest.get("output_name", run_id)
        labels = manifest.get("labels", [])

        # build assembly view
        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=f"Label Run: {run_id}",
            assembly_subtitle=f"Sheet spec: {sheet_spec}",
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        # assemble intermediate Markdown — one section per slot
        lines: list[str] = []
        lines.append(f"# Label Run: {run_id}")
        lines.append(f"**Sheet spec:** {sheet_spec}  ")
        lines.append(f"**Profile:** {profile}  ")
        lines.append(f"**Labels:** {len(labels)}  ")
        lines.append("")

        for lbl in sorted(labels, key=lambda l: l.get("slot", 9999)):
            slot = lbl["slot"]
            src_path = Path(lbl["source"])
            uid = f"slot-{slot}"

            assembly.source_order.append(uid)
            assembly.source_paths[uid] = str(src_path)
            assembly.source_roles[uid] = "label"

            lines.append(f"\\newpage\\section{{Slot {slot}}}")

            if src_path.exists():
                assembly.source_digests[uid] = _sha256_hex(src_path)
                raw_text = src_path.read_text()
                fm, body = _split_frontmatter_and_body(raw_text)

                if fm:
                    lines.append("**Label metadata:**  ")
                    for key, value in sorted(fm.items()):
                        lines.append(f"- `{key}`: {value}")
                    lines.append("")

                lines.append(body.rstrip())
            else:
                lines.append(f"*[Label source not found: {src_path}]*")

            lines.append("")

        assembled_content = "\n".join(lines)
        render_source = _write_temp_markdown(f"label_{run_id}", assembled_content)

        plan = ProjectionPlan(
            profile_id=profile,
            render_id=run_id,
            render_source=render_source,
            title=output_name,
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "slot": int(uid.split("-")[1]) if uid.startswith("slot-") else 0,
                    "path": assembly.source_paths.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            boundary_assertions={
                **_manifest_boundary_assertions(render_plan),
                "layout_mode": "content_driven_placeholder",
                "grid_validated": False,
                "warnings": [
                    "Label run currently renders slot-ordered content as a synthetic placeholder document.",
                    "Physical Avery/grid placement remains content-driven and is not validated by this compiler.",
                ],
            },
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("run_id"):
            errors.append("missing run_id")

        if not manifest.get("sheet_spec"):
            errors.append("missing sheet_spec")

        labels = manifest.get("labels")
        if not labels or not isinstance(labels, list):
            errors.append("labels must be a non-empty list")
        else:
            seen_slots = set()
            for i, lbl in enumerate(labels):
                slot = lbl.get("slot")
                if slot is None or not isinstance(slot, int) or slot < 1:
                    errors.append(f"label[{i}] missing or invalid slot")
                elif slot in seen_slots:
                    errors.append(f"label[{i}] duplicate slot: {slot}")
                else:
                    seen_slots.add(slot)

                src = lbl.get("source")
                if not src:
                    errors.append(f"label[{i}] missing source")
                elif not Path(src).exists():
                    errors.append(f"label[{i}] source not found: {src}")

        return errors


class StickerSheetCompiler(ManifestCompiler):
    """Compile a sticker_sheet / sticker_sheet_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    with cell-ordered sticker content.
    """

    kind = "sticker_sheet"
    schema_version = "sticker_sheet_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        sheet_id = manifest["sheet_id"]
        profile = manifest["profile"]
        layout = manifest.get("layout", {})
        grid = layout.get("grid", [1, 1])
        cell_size = layout.get("cell_size", [2.5, 2.5])
        show_cut = layout.get("show_cut_lines", True)
        cells = manifest.get("cells", [])

        max_row, max_col = grid[0] if len(grid) >= 1 else 1, grid[1] if len(grid) >= 2 else 1

        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=f"Sticker Sheet: {sheet_id}",
            assembly_subtitle=f"Grid: {max_row}×{max_col}",
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        lines: list[str] = []
        lines.append(f"# Sticker Sheet: {sheet_id}")
        lines.append(f"**Grid:** {max_row}×{max_col}  ")
        lines.append(f"**Cell size:** {cell_size[0] if cell_size else '?'}in × {cell_size[1] if len(cell_size)>1 else '?'}in  ")
        lines.append(f"**Cut lines:** {'on' if show_cut else 'off'}  ")
        lines.append(f"**Cells:** {len(cells)}  ")
        lines.append("")

        for cell in cells:
            pos = cell.get("position", [0, 0])
            row, col = pos[0] if len(pos) >= 1 else 0, pos[1] if len(pos) >= 2 else 0
            uid = f"cell-{row}-{col}"
            content = cell.get("content", "")
            source = cell.get("source")
            image = cell.get("image")

            assembly.source_order.append(uid)
            assembly.source_roles[uid] = "sticker"

            lines.append(f"\\newpage\\section{{Cell [{row},{col}]}}")

            if source:
                src_path = Path(source)
                assembly.source_paths[uid] = str(src_path)
                if src_path.exists():
                    assembly.source_digests[uid] = _sha256_hex(src_path)
                    lines.append(src_path.read_text().rstrip())
                else:
                    lines.append(f"*[Source not found: {source}]*")
            elif content:
                assembly.source_paths[uid] = f"inline://{uid}"
                assembly.source_digests[uid] = hashlib.sha256(content.encode()).hexdigest()
                lines.append(content)

            if image:
                img_path = image
                lines.append(f"![]({img_path})")

            lines.append("")

        assembled_content = "\n".join(lines)
        render_source = _write_temp_markdown(f"sticker_{sheet_id}", assembled_content)

        plan = ProjectionPlan(
            profile_id=profile,
            render_id=sheet_id,
            render_source=render_source,
            title=sheet_id,
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "path": assembly.source_paths.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            boundary_assertions={
                **_manifest_boundary_assertions(render_plan),
                "layout_mode": "content_driven_placeholder",
                "grid_validated": False,
                "warnings": [
                    "Sticker sheet currently renders cell-ordered content as a synthetic placeholder document.",
                    "Physical sticker grid placement remains content-driven and is not validated by this compiler.",
                ],
            },
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("sheet_id"):
            errors.append("missing sheet_id")

        if not manifest.get("profile"):
            errors.append("missing profile")

        layout = manifest.get("layout", {})
        grid = layout.get("grid", [])
        if not isinstance(grid, list) or len(grid) < 2 or not all(isinstance(g, int) and g > 0 for g in grid):
            errors.append("layout.grid must be a list of 2 positive integers")

        cells = manifest.get("cells")
        if not cells or not isinstance(cells, list):
            errors.append("cells must be a non-empty list")
        else:
            max_row = grid[0] if len(grid) >= 1 else 0
            max_col = grid[1] if len(grid) >= 2 else 0
            seen_positions = set()
            for i, cell in enumerate(cells):
                pos = cell.get("position")
                if not pos or not isinstance(pos, list) or len(pos) < 2:
                    errors.append(f"cell[{i}] missing or invalid position")
                else:
                    row, col = pos[0], pos[1]
                    if not (0 <= row < max_row and 0 <= col < max_col):
                        errors.append(f"cell[{i}] position [{row},{col}] out of grid bounds {max_row}×{max_col}")
                    pkey = (row, col)
                    if pkey in seen_positions:
                        errors.append(f"cell[{i}] duplicate position [{row},{col}]")
                    seen_positions.add(pkey)

                if not cell.get("content") and not cell.get("source") and not cell.get("image"):
                    errors.append(f"cell[{i}] has no content, source, or image")

        return errors


class ForgePacketReviewCompiler(ManifestCompiler):
    """Compile a forge_packet_review / packet_review_manifest_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    that projects packet lifecycle state for review: goal, constraints, plan,
    state, progress, validation, and questions.
    """

    kind = "forge_packet_review"
    schema_version = "packet_review_manifest_v1"

    DEFAULT_INCLUDE = [
        "GOAL.md",
        "CONSTRAINTS.md",
        "PLAN.md",
        "STATE.json",
        "PROGRESS.md",
        "VALIDATION.md",
    ]

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        profile = manifest["profile"]
        pkt = manifest.get("packet", {})
        pkt_path = Path(pkt.get("path", ""))
        includes = pkt.get("include", self.DEFAULT_INCLUDE)
        exclude_gen = pkt.get("exclude_generated", True)
        render_cfg = manifest.get("render", {})

        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=f"Packet Review: {pkt_path.name if pkt_path else 'unknown'}",
            assembly_subtitle=str(pkt_path),
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        lines: list[str] = []
        lines.append(f"# Packet Review: {pkt_path.name if pkt_path else 'Packet State'}")
        lines.append(f"**Packet path:** `{pkt_path}`")
        lines.append(f"**Generated:** import time (placeholder)")
        lines.append("")

        # Include each file in the include list
        for inc_name in includes:
            inc_path = pkt_path / inc_name
            uid = inc_name.replace(".", "_")
            assembly.source_order.append(uid)
            assembly.source_paths[uid] = str(inc_path)
            assembly.source_roles[uid] = "packet_surface"

            if not inc_path.exists():
                lines.append("\\newpage")
                lines.append(f"# `{inc_name}`")
                lines.append(f"*[File not found: {inc_path}]*")
                lines.append("")
                continue

            assembly.source_digests[uid] = _sha256_hex(inc_path)
            lines.append("\\newpage")
            lines.append(f"# `{inc_name}`")

            if inc_path.suffix == ".json":
                import json
                try:
                    data = json.loads(inc_path.read_text())
                    if isinstance(data, dict):
                        lines.append("**JSON summary**")
                        lines.append("")
                        for k, v in data.items():
                            if isinstance(v, (str, int, float, bool)) or v is None:
                                lines.append(f"- **{k}**: {v}")
                            elif isinstance(v, list):
                                lines.append(f"- **{k}**: list[{len(v)}]")
                            elif isinstance(v, dict):
                                lines.append(f"- **{k}**: object[{len(v)} keys]")
                        lines.append("")
                    else:
                        lines.append(f"*JSON value of type {type(data).__name__}*\n")
                except json.JSONDecodeError:
                    lines.append("*Invalid JSON; raw content omitted from packet-review fixture render.*")
            else:
                lines.append(inc_path.read_text())
            lines.append("")

        # optionally include questions
        if render_cfg.get("include_questions", True):
            q_path = pkt_path / "QUESTIONS.md"
            if q_path.exists():
                uid = "QUESTIONS_md"
                assembly.source_order.append(uid)
                assembly.source_paths[uid] = str(q_path)
                assembly.source_roles[uid] = "packet_surface"
                assembly.source_digests[uid] = _sha256_hex(q_path)
                lines.append("\\newpage")
                lines.append("# `QUESTIONS.md`")
                lines.append(q_path.read_text())
                lines.append("")

        # optionally include dirty state summary
        if render_cfg.get("include_dirty_state_summary", True):
            ds_path = pkt_path / "DIRTY_STATE.json"
            if ds_path.exists():
                import json
                uid = "DIRTY_STATE_json"
                assembly.source_order.append(uid)
                assembly.source_paths[uid] = str(ds_path)
                assembly.source_roles[uid] = "packet_surface"
                assembly.source_digests[uid] = _sha256_hex(ds_path)
                lines.append("\\newpage")
                lines.append("# `DIRTY_STATE.json`")
                data = json.loads(ds_path.read_text())
                lines.append("**JSON summary**")
                lines.append("")
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, (str, int, float, bool)) or v is None:
                            lines.append(f"- **{k}**: {v}")
                        elif isinstance(v, list):
                            lines.append(f"- **{k}**: list[{len(v)}]")
                        elif isinstance(v, dict):
                            lines.append(f"- **{k}**: object[{len(v)} keys]")
                lines.append("")

        assembled_content = "\n".join(lines)
        render_source = _write_temp_markdown(f"pkt_review_{pkt_path.name if pkt_path else 'unknown'}", assembled_content)

        plan = ProjectionPlan(
            profile_id=profile,
            render_id=f"review-{pkt_path.name}" if pkt_path else "review-unknown",
            render_source=render_source,
            title=f"Packet Review: {pkt_path.name}" if pkt_path else "Packet Review",
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "path": assembly.source_paths.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            boundary_assertions={
                **_manifest_boundary_assertions(render_plan),
                "projection_mode": "packet_review",
                "packet_review_fixture": True,
                "include_questions": render_cfg.get("include_questions", True),
                "include_dirty_state_summary": render_cfg.get("include_dirty_state_summary", True),
            },
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("profile"):
            errors.append("missing profile")

        pkt = manifest.get("packet")
        if not pkt or not isinstance(pkt, dict):
            errors.append("packet must be a dict")
        else:
            pkt_path = pkt.get("path")
            if not pkt_path:
                errors.append("packet.path is required")
            elif not Path(pkt_path).is_dir():
                errors.append(f"packet.path is not a directory: {pkt_path}")

        return errors
