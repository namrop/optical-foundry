"""Source preparation: every rewrite of the source before pandoc reads it.

Architecture review 2026-10-01, candidate 3; keeper ruling 01a0f930-407c:
"1. yes a profile should be able to declare which it uses / 2. thorough /
3. no, web is not in scope for now."

Before this module, ``PandocRenderer.render()`` ran ten rewrites in an order only
it knew, each a private method that tests reached into. Now:

* the ten steps are named, in one fixed order (``STEPS``), and each is a
  function here that a test can call directly;
* ``prepare(plan, profile, out_dir)`` runs them and is the renderer's only call;
* a profile may declare the steps it uses (``source_preparation`` in
  ``engine/profile_resolver.PROFILE_SPECS``). A profile that declares nothing
  gets every step, which is the behaviour every render had before;
* the evidence records, per step, whether it ran and whether it changed the
  source (``render_metadata.source_preparation``).

Two kinds of step, run in this order:

1. **plan steps** rewrite the document and may add figures and evidence; the
   rewritten file becomes ``plan.render_source``:
   codex_edition, layout_images, mermaid, vega, d2, graphviz, emoji.
2. **render-copy steps** make a render-only copy for pandoc and leave the plan's
   source as the record of what was rendered: stationery_opening,
   titlepage_background_guard, resource_pinning.

Every step leaves the author's file untouched; each writes its rewrite into the
render's output directory. PDF output only (web is out of scope, per the ruling).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import yaml

from engine.codex_editions import (
    CodexEditionRenderError,
    edition_from_source_frontmatter,
    preprocess_codex_edition_blocks,
    source_contains_codex_edition_markers,
    source_contains_codex_editorial_callouts,
)
from engine.d2 import D2RenderError, preprocess_d2_blocks
from engine.emoji_substitution import preprocess_emoji_substitutions
from engine.graphviz import GraphvizRenderError, preprocess_graphviz_blocks
from engine.layout_images import LayoutImageRenderError, preprocess_layout_image_blocks
from engine.mermaid import MermaidRenderError, preprocess_mermaid_blocks
from engine.profile_resolver import LOCAL_IMPORT, ResolvedProfile
from engine.projection_plan import ProjectionPlan
from engine.resource_roots import (
    ResolvedResourceRoot,
    TEMPLATE_RESOURCE_KEYS,
    effective_resource_roots,
    pin_render_resources,
    resource_resolution_evidence,
    resource_root_paths,
)
from engine.vega import VegaRenderError, preprocess_vega_blocks

PLAN_STEPS = ("codex_edition", "layout_images", "mermaid", "vega", "d2", "graphviz", "emoji")
RENDER_COPY_STEPS = ("stationery_opening", "titlepage_background_guard", "resource_pinning")
STEPS = PLAN_STEPS + RENDER_COPY_STEPS

# A step that cannot prepare the source raises one of these; the renderer turns
# it into an error evidence record (stage "source-preprocessor").
PREPARATION_ERRORS: tuple[type[Exception], ...] = (
    CodexEditionRenderError, LayoutImageRenderError, MermaidRenderError,
    VegaRenderError, D2RenderError, GraphvizRenderError,
)


def declared_steps(profile: ResolvedProfile) -> tuple[tuple[str, ...], str]:
    """(the steps this profile runs, in engine order; who said so)."""
    declared = getattr(profile, "source_preparation", None)
    if declared is None:
        return STEPS, "default"
    return tuple(step for step in STEPS if step in declared), "profile"


def validate_declaration(steps: Any) -> list[str]:
    if not isinstance(steps, (list, tuple)):
        return ["source_preparation must be a list of step names"]
    unknown = [s for s in steps if s not in STEPS]
    return [f"source_preparation: unknown step(s) {unknown}; known: {list(STEPS)}"] if unknown else []


@dataclass
class PreparedSource:
    plan: ProjectionPlan              # plan after the plan steps (render_source = the rendered document)
    source: Path                      # the file pandoc reads
    resource_roots: list[ResolvedResourceRoot]
    resource_resolution: dict[str, Any]
    record: dict[str, Any] = field(default_factory=dict)


def prepare(plan: ProjectionPlan, profile: ResolvedProfile, out_dir: Path) -> PreparedSource:
    """Run the profile's steps, in engine order. Raises one of PREPARATION_ERRORS."""
    steps, declared_by = declared_steps(profile)
    log: list[dict[str, Any]] = []
    for name in PLAN_STEPS:
        if name not in steps:
            log.append({"step": name, "ran": False, "changed": False})
            continue
        before = plan.render_source
        plan = PLAN_STEP_FUNCTIONS[name](plan, out_dir, profile)
        log.append({"step": name, "ran": True, "changed": plan.render_source != before})

    roots = effective_resource_roots(plan, profile, out_dir)
    resolution = resource_resolution_evidence(plan, roots)
    source = plan.render_source.resolve()

    def copy_step(name: str, fn: Callable[[], Path]) -> None:
        nonlocal source
        if name not in steps:
            log.append({"step": name, "ran": False, "changed": False})
            return
        before = source
        source = fn()
        log.append({"step": name, "ran": True, "changed": source != before})

    copy_step("stationery_opening",
              lambda: stationery_opening(source, out_dir, plan.render_id, profile.profile_family))
    copy_step("titlepage_background_guard",
              lambda: titlepage_background_guard(source, out_dir, plan.render_id))
    pins: dict[str, Any] = {"pinned": [], "unpinned": [], "warnings": []}

    def _pin() -> Path:
        nonlocal pins
        pinned, pins = resource_pinning(source, out_dir, plan.render_id, roots, profile.render_environment.cwd)
        return pinned

    copy_step("resource_pinning", _pin)
    resolution["raw_latex_pins"] = pins
    resolution["warnings"] = [*resolution["warnings"], *pins.pop("warnings")]
    return PreparedSource(
        plan=plan, source=source, resource_roots=roots, resource_resolution=resolution,
        record={"declared_by": declared_by, "steps": log},
    )


# --------------------------------------------------------------------------
# Plan steps
# --------------------------------------------------------------------------

def _with_figures(plan: ProjectionPlan, source: Path, figures: list[dict[str, Any]], boundary: dict[str, Any]) -> ProjectionPlan:
    return replace(plan, render_source=source, figure_inventory=[*plan.figure_inventory, *figures],
                   boundary_assertions=boundary)


def pdf_latex_output(plan: ProjectionPlan, profile: ResolvedProfile) -> bool:
    """True when the render is a PDF through a LaTeX template (raw LaTeX is safe to emit)."""
    return (
        str(plan.output_format).lower() == "pdf"
        and plan.output_extension == ".pdf"
        and profile.template_path.suffix.lower() == ".tex"
    )


def codex_edition(plan: ProjectionPlan, out_dir: Path, profile: ResolvedProfile) -> ProjectionPlan:
    """Select one edition of a source with edition variants, before other preprocessors.

    The profile declares editions (map C1) and its marker namespace (map C2). Fail
    closed: a profile that declares no editions refuses a source carrying edition
    markers in any namespace, or a requested edition, rather than leak every edition
    into a proof. Sources without markers are unchanged.
    """
    if not plan.render_source.exists():
        return plan
    from engine.markers import ANY_EDITION_MARKER_RE, prefix_of

    editions = getattr(profile, "editions", None)
    prefix = prefix_of(getattr(profile, "markers", None))
    edition, strip_callouts = edition_from_source_frontmatter(plan.render_source)
    if editions is None:
        text = plan.render_source.read_text(encoding="utf-8", errors="ignore")
        if ANY_EDITION_MARKER_RE.search(text) or edition or strip_callouts:
            raise CodexEditionRenderError(
                f"edition controls need a profile that declares editions; "
                f"{profile.canonical_profile_id} declares none"
            )
        return plan
    has_markers = source_contains_codex_edition_markers(plan.render_source, prefix)
    has_callouts = source_contains_codex_editorial_callouts(plan.render_source)
    format_callouts = has_callouts and not strip_callouts
    if not has_markers and not strip_callouts and not format_callouts:
        return plan
    result = preprocess_codex_edition_blocks(
        plan.render_source, out_dir, plan.render_id, edition,
        strip_editorial_callouts=strip_callouts, format_editorial_callouts=format_callouts,
        prefix=prefix, labels=editions.get("labels"),
    )
    if not result.changed:
        return plan
    boundary = dict(plan.boundary_assertions)
    warnings = [*boundary.get("warnings", []), *result.warnings]
    boundary.update(
        {
            "codex_edition_preprocessor_enabled": True,
            "codex_edition_profile_scope": profile.canonical_profile_id,
            "codex_edition": result.edition,
            "codex_edition_variant_count": result.variant_count,
            "codex_edition_selected_count": result.selected_count,
            "codex_edition_fallback_count": result.fallback_count,
            "codex_edition_selected_variant_ids": result.selected_variant_ids,
            "codex_edition_fallback_variant_ids": result.fallback_variant_ids,
            "codex_editorial_callouts_stripped": result.editorial_callouts_stripped,
            "codex_editorial_callouts_formatted": result.editorial_callouts_formatted,
            "codex_edition_render_mode": "pre_pandoc_comment_sentinel_culler",
        }
    )
    if warnings:
        boundary["warnings"] = warnings
    return replace(plan, render_source=result.rewritten_source, boundary_assertions=boundary)


def layout_images(plan: ProjectionPlan, out_dir: Path, profile: ResolvedProfile) -> ProjectionPlan:
    """Rewrite fenced `of-image` blocks into wrapfig/TikZ/shipout raw LaTeX.

    Opt-in: ordinary Markdown images keep their normal behaviour.
    """
    if not plan.render_source.exists() or not pdf_latex_output(plan, profile):
        return plan
    if plan.manifest_resource_roots:
        layout_roots = resource_root_paths(effective_resource_roots(plan, profile, out_dir))
    else:
        # The clean-HEAD layout search order when the manifest names no roots:
        # authored source, render output, then the profile/source compatibility roots.
        layout_roots = [
            plan.render_source.resolve().parent,
            Path(out_dir).resolve(),
            LOCAL_IMPORT,
            *profile.asset_roots,
            *plan.source_resource_roots,
        ]
    result = preprocess_layout_image_blocks(
        plan.render_source, out_dir, plan.render_id, layout_roots,
        force_graphicspath=bool(plan.manifest_resource_roots),
    )
    if not result.changed:
        return plan
    boundary = dict(plan.boundary_assertions)
    figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
    for entry in result.figure_inventory:
        kind = str(entry.get("kind", "layout_image"))
        figure_count_by_kind[kind] = figure_count_by_kind.get(kind, 0) + 1
    layout_image_count = sum(1 for entry in result.figure_inventory if entry.get("kind") == "layout_image")
    image_initials = [entry for entry in result.figure_inventory if entry.get("kind") == "image_initial"]
    warnings = [*boundary.get("warnings", []), *result.warnings]
    updates = {
        "layout_image_supported_profiles": "pdf_latex_profiles",
        "layout_image_profile_family": profile.profile_family,
        "layout_image_canonical_profile": profile.canonical_profile_id,
        "layout_image_render_mode": "pre_pandoc_raw_latex",
        "layout_image_graphicspath_roots": result.graphicspath_roots,
        "figure_count_by_kind": figure_count_by_kind,
    }
    if layout_image_count:
        updates.update({"layout_images_enabled": True, "layout_image_count": layout_image_count})
    if image_initials:
        updates.update(
            {
                "image_initials_enabled": True,
                "image_initial_count": len(image_initials),
                "image_initial_default_alignment": image_initials[0].get("alignment", "bottom"),
            }
        )
    boundary.update(updates)
    if warnings:
        boundary["warnings"] = warnings
    return _with_figures(plan, result.rewritten_source, result.figure_inventory, boundary)


def _generated_figures(plan: ProjectionPlan, result: Any, kind: str, prefix: str, count_key: str,
                       *, figure_warnings: bool) -> ProjectionPlan:
    boundary = dict(plan.boundary_assertions)
    figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
    figure_count_by_kind[kind] = figure_count_by_kind.get(kind, 0) + len(result.figure_inventory)
    boundary.update(
        {
            "generated_figures_enabled": True,
            "figure_count_by_kind": figure_count_by_kind,
            f"{prefix}_enabled": True,
            count_key: len(result.figure_inventory),
            f"{prefix}_theme": result.theme,
            f"{prefix}_render_mode": "pre_pandoc_generated_asset",
        }
    )
    if figure_warnings:
        warnings = [warning for fig in result.figure_inventory for warning in fig.get("warnings", [])]
        if warnings:
            boundary["warnings"] = [*list(boundary.get("warnings", [])), *warnings]
    return _with_figures(plan, result.rewritten_source, result.figure_inventory, boundary)


def mermaid(plan: ProjectionPlan, out_dir: Path, profile: ResolvedProfile | None = None, *,
            renderer=None, output_format: str = "pdf") -> ProjectionPlan:
    """Pre-render Mermaid fences into generated figures."""
    if not plan.render_source.exists():
        return plan
    result = preprocess_mermaid_blocks(
        plan.render_source, profile_id=plan.profile_id, output_dir=out_dir, render_id=plan.render_id,
        renderer=renderer, output_format=output_format,
    )
    if not result.changed:
        return plan
    return _generated_figures(plan, result, "mermaid", "mermaid", "mermaid_diagram_count", figure_warnings=False)


def vega(plan: ProjectionPlan, out_dir: Path, profile: ResolvedProfile | None = None, *,
         renderer=None, output_format: str = "pdf") -> ProjectionPlan:
    """Pre-render full Vega fences into generated figures."""
    if not plan.render_source.exists():
        return plan
    settings = plan.document_settings
    result = preprocess_vega_blocks(
        plan.render_source, profile_id=plan.profile_id, output_dir=out_dir, render_id=plan.render_id,
        renderer=renderer, output_format=output_format,
        figure_captions=bool(settings.figure_captions) if settings else False,
        figure_numbering=bool(settings.figure_numbering) if settings else False,
        figure_numbering_section=bool(settings.figure_numbering_section) if settings else False,
    )
    if not result.changed:
        return plan
    return _generated_figures(plan, result, "vega", "vega", "vega_chart_count", figure_warnings=True)


def d2(plan: ProjectionPlan, out_dir: Path, profile: ResolvedProfile | None = None, *,
       renderer=None, output_format: str = "svg") -> ProjectionPlan:
    """Pre-render D2 diagram fences into generated figures."""
    if not plan.render_source.exists():
        return plan
    result = preprocess_d2_blocks(
        plan.render_source, profile_id=plan.profile_id, output_dir=out_dir, render_id=plan.render_id,
        renderer=renderer, output_format=output_format,
    )
    if not result.changed:
        return plan
    return _generated_figures(plan, result, "d2", "d2", "d2_diagram_count", figure_warnings=True)


def graphviz(plan: ProjectionPlan, out_dir: Path, profile: ResolvedProfile | None = None, *,
             renderer=None, output_format: str = "svg") -> ProjectionPlan:
    """Pre-render Graphviz/DOT fences into generated figures."""
    if not plan.render_source.exists():
        return plan
    result = preprocess_graphviz_blocks(
        plan.render_source, profile_id=plan.profile_id, output_dir=out_dir, render_id=plan.render_id,
        renderer=renderer, output_format=output_format,
    )
    if not result.changed:
        return plan
    return _generated_figures(plan, result, "graphviz_dot", "graphviz_dot", "graphviz_dot_diagram_count",
                              figure_warnings=True)


def emoji(plan: ProjectionPlan, out_dir: Path, profile: ResolvedProfile) -> ProjectionPlan:
    """Rewrite registered glyphs: emoji to vendored images, others to fallback fonts."""
    if not plan.render_source.exists() or not pdf_latex_output(plan, profile):
        return plan
    result = preprocess_emoji_substitutions(plan.render_source, out_dir, plan.render_id)
    if not result.changed:
        return plan
    boundary = dict(plan.boundary_assertions)
    figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
    total = 0
    counts_by_key: dict[str, int] = {}
    fallback_counts: dict[str, int] = {}
    for entry in result.inventory:
        kind = str(entry.get("kind", "emoji_asset"))
        if kind == "glyph_fallback_font":
            fallback_counts[str(entry["family"])] = int(entry.get("characters", 0))
            continue
        count = int(entry.get("count", 0))
        figure_count_by_kind[kind] = figure_count_by_kind.get(kind, 0) + count
        total += count
        counts_by_key[str(entry.get("asset_key", ""))] = count
    warnings = [*boundary.get("warnings", []), *result.warnings]
    boundary.update(
        {
            "emoji_policy": "vendored_image_assets",
            "emoji_asset_family": "noto_emoji",
            "emoji_render_mode": "pre_pandoc_raw_latex_inline_image",
            "emoji_substitution_count": total,
            "emoji_substitution_counts_by_key": counts_by_key,
            "emoji_asset_paths": result.asset_paths,
            "host_emoji_fonts_required": False,
            "figure_count_by_kind": figure_count_by_kind,
            # Glyph registry (engine/glyph_registry.py): characters set in a
            # vendored fallback font, and the per-render filter that lowers
            # registered glyphs inside inline code.
            "glyph_fallback_characters_by_family": fallback_counts,
            "glyph_code_lua_filter": str(result.lua_filter) if result.lua_filter else "",
        }
    )
    if warnings:
        boundary["warnings"] = warnings
    return _with_figures(plan, result.rewritten_source, result.inventory, boundary)


PLAN_STEP_FUNCTIONS: dict[str, Callable[[ProjectionPlan, Path, ResolvedProfile], ProjectionPlan]] = {
    "codex_edition": codex_edition,
    "layout_images": layout_images,
    "mermaid": mermaid,
    "vega": vega,
    "d2": d2,
    "graphviz": graphviz,
    "emoji": emoji,
}


# --------------------------------------------------------------------------
# Render-copy steps
# --------------------------------------------------------------------------

def _split_frontmatter(text: str) -> tuple[dict[str, Any], str, int] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    try:
        frontmatter = yaml.safe_load(text[4:end]) or {}
    except Exception:
        return None
    if not isinstance(frontmatter, dict):
        return None
    return frontmatter, text[end + 4:], end


def stationery_opening(render_source: Path, out_dir: Path, render_id: str, profile_family: str) -> Path:
    """Render-only copy with the duplicate salutation (and signed closing) removed.

    Atrium letter sources often keep `variables.opening` for templates while
    also keeping the salutation in body Markdown for readability. The
    stationery templates render `opening` themselves, so the first body line is
    dropped from the render copy when it matches the template opening.
    """
    if profile_family != "stationery_art" or not render_source.exists():
        return render_source
    text = render_source.read_text(encoding="utf-8", errors="ignore")
    split = _split_frontmatter(text)
    if split is None:
        return render_source
    frontmatter, body, end = split
    variables = frontmatter.get("variables", {})
    if not isinstance(variables, dict):
        return render_source
    opening = variables.get("opening") or frontmatter.get("opening")
    if not isinstance(opening, str) or not opening.strip():
        return render_source

    def _plain_markdown_line(line: str) -> str:
        # Salutations are sometimes kept source-readable as **My love,** while
        # the template variable is unadorned: compare the text, not the emphasis.
        return re.sub(r"^([*_`]+)(.*)\1$", r"\2", line.strip()).strip()

    leading_newlines = len(body) - len(body.lstrip("\n"))
    body_after_leading = body[leading_newlines:]
    first_line, sep, rest = body_after_leading.partition("\n")
    normalized_body = "\n" + body_after_leading.lstrip("\n")
    if sep and _plain_markdown_line(first_line) == _plain_markdown_line(opening):
        normalized_body = "\n" + rest.lstrip("\n")

    lines = normalized_body.splitlines()
    nonempty = [(idx, line.strip()) for idx, line in enumerate(lines) if line.strip()]
    if len(nonempty) >= 2 and nonempty[-1][1] in {"Luis", "Luis E. Ramirez"}:
        closing_idx, closing_line = nonempty[-2]
        if closing_line.startswith("With ") or closing_line.endswith(","):
            normalized_body = "\n" + "\n".join(lines[:closing_idx]).strip() + "\n"
    path = out_dir / f"{render_id}.stationery_source.md"
    path.write_text(text[: end + 4] + normalized_body, encoding="utf-8")
    return path


def safe_frontmatter_resource_path(value: Any) -> bool:
    """A relative PNG/JPG/PDF path with nothing LaTeX or a shell could interpret."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value or "://" in value:
        return False
    if any(ch in value for ch in ("{", "}", "$", "`")):
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf"}


def titlepage_background_guard(render_source: Path, out_dir: Path, render_id: str) -> Path:
    """Render-only copy with unsafe title-page background paths removed.

    `titlepage_background_image` is interpolated into a LaTeX `\\includegraphics`
    path, from top-level YAML or nested `variables:`; keep only relative
    PNG/JPG/PDF paths.
    """
    if not render_source.exists():
        return render_source
    text = render_source.read_text(encoding="utf-8", errors="ignore")
    split = _split_frontmatter(text)
    if split is None:
        return render_source
    frontmatter, body, _end = split
    changed = False
    if "titlepage_background_image" in frontmatter and not safe_frontmatter_resource_path(
        frontmatter.get("titlepage_background_image")
    ):
        frontmatter.pop("titlepage_background_image", None)
        changed = True
    variables = frontmatter.get("variables")
    if isinstance(variables, dict) and "titlepage_background_image" in variables:
        if not safe_frontmatter_resource_path(variables.get("titlepage_background_image")):
            variables = dict(variables)
            variables.pop("titlepage_background_image", None)
            frontmatter["variables"] = variables
            changed = True
    if not changed:
        return render_source
    path = out_dir / f"{render_id}.titlepage_guarded.md"
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip()
    path.write_text(f"---\n{fm_yaml}\n---{body}", encoding="utf-8")
    return path


def resource_pinning(
    render_source: Path,
    out_dir: Path,
    render_id: str,
    roots: list[ResolvedResourceRoot],
    latex_cwd: Path | None,
) -> tuple[Path, dict[str, Any]]:
    """Render-only copy whose relative image references name the files the root chain picks.

    LaTeX's own search would otherwise try the profile folder first
    (engine/resource_roots.py, "Raw-LaTeX resource pinning").
    """
    if not render_source.exists():
        return render_source, {"pinned": [], "unpinned": [], "warnings": []}
    text = render_source.read_text(encoding="utf-8", errors="ignore")
    pinned_text, record = pin_render_resources(text, roots, latex_cwd=latex_cwd, template_keys=TEMPLATE_RESOURCE_KEYS)
    if pinned_text == text:
        return render_source, record
    path = out_dir / f"{render_id}.resources_pinned.md"
    path.write_text(pinned_text, encoding="utf-8")
    return path, record
