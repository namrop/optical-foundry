r"""Preprocess Optical Foundry layout-image source blocks.

The source-facing surface is an explicit fenced block, not default Markdown image
behavior:

```of-image
path: assets/portrait.png
placement: wrap        # wrap | absolute | inline | block
align: right           # wrap only: left | right
width: 0.34\textwidth
edge: vignette         # none | fade | vignette | soft
gap: 2\baselineskip    # block only: vertical envelope, defaults to the hinge's
auto_trim: true        # block only: crop the blank margin the asset ships
caption: Optional caption
```

The preprocessor rewrites the block into guarded raw LaTeX. It is intentionally
PDF/LaTeX-oriented: Markdown remains the canonical source surface, while the
render-only copy carries wrapfig/TikZ/eso-pic commands for Pandoc.

Displayed images (`placement: block`, and raw centered `\includegraphics`
vignettes written straight into source) additionally get a measured whitespace
contract — see the `_BLOCK_IMAGE_GAP_DEFAULT` block below for the ruling, the
measurements behind it, and what is deliberately left alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import re


class LayoutImageRenderError(RuntimeError):
    """Raised when an `of-image` block is unsafe or malformed."""


@dataclass(frozen=True)
class LayoutImagePreprocessResult:
    changed: bool
    rewritten_source: Path
    figure_inventory: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    graphicspath_roots: list[str] = field(default_factory=list)


_BLOCK_RE = re.compile(r"^```of-image\s*\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL)
_INITIAL_BLOCK_RE = re.compile(r"^```of-initial\s*\n(?P<body>.*?)^```\s*\n?", re.MULTILINE | re.DOTALL)
_RAW_LATEX_RESOURCE_RE = re.compile(
    r"\\(?:includegraphics|OFSectionDividerBackground|CodexFloatingPlate|OFOuterRail|OFBottomRail|OFEdgeOrnament)\b"
)
_SAFE_DIMENSION_RE = re.compile(
    r"^-?(?:\\(?:linewidth|textwidth|textheight|paperwidth|paperheight|baselineskip)|(?:0(?:\.0+)?|0?\.\d+|[1-9]\d*(?:\.\d+)?)(?:\\(?:linewidth|textwidth|textheight|paperwidth|paperheight|baselineskip)|in|cm|mm|pt|em|ex))$"
)
_SAFE_OPACITY_RE = re.compile(r"^(?:0(?:\.\d+)?|1(?:\.0+)?)$")
_ALLOWED_PLACEMENTS = {"wrap", "absolute", "inline", "block"}
_ALLOWED_ALIGN = {"left": "l", "right": "r"}
_ALLOWED_ANCHORS = {"north east", "north west", "south east", "south west", "center"}
_ALLOWED_EDGES = {"", "none", "fade", "vignette", "soft", "soft-edge", "soft_edge"}
_ALLOWED_INITIAL_ALIGNMENTS = {"bottom", "top"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

# --- Displayed-image vertical envelope (Luis-ruled 2026-08-11, build-64 proof) ---
#
# Folio 168: "there is too much whitespace around the image. it should be
# comparable to a hinge. across the whole work. [two other object vignettes]
# are instances too."
#
# The target is measured, not invented. A hinge ornament is emitted by
# profiles/40_latex_import/filters/codex0_composition.lua as
#
#   \CodexBreakOrnament -> \par\vspace{G}{\centering <glyph>\par}\vspace{G}
#   hinge_ornament_gap  = 2\baselineskip   (26.9pt at the book's 13.44pt leading)
#
# and on Vol I folio 168 of build 64 that hinge measures 33.6pt of ink-to-ink air
# above it and 37.7pt below. The block image four inches down the
# same page measured 63.6pt above and 58.8pt below — roughly 1.7x a hinge.
#
# Two separate causes, both addressed here:
#
#   1. ENVELOPE. `placement: block` was emitted as a bare `\begin{center}`, so its
#      vertical space was LaTeX's trivlist \topsep + \partopsep + \parskip. That is
#      smaller than a hinge AND it carries stretch, so no two displayed images in
#      the book agreed with each other or with the ornament ladder. Displayed
#      images now use the hinge's own rigid envelope, by way of the
#      `OFDisplayedFigure` environment defined below.
#
#   2. THE ASSET'S OWN MARGIN — the larger share. Object extracts are exported on a
#      generous canvas, so the PNG ships its whitespace inside the image box where
#      no LaTeX skip can reach it: one vignette 24%/29% top/bottom, another
#      27%/32%, a third 35%/42%. A fourth vignette is
#      alpha-tight but fades below visibility ~36% before its top edge, which reads
#      the same way on paper. That margin is now measured and cropped at render
#      time, with the declared width scaled by the retained fraction so the VISIBLE
#      object keeps exactly the size it has today — this removes whitespace, never
#      resizes artwork.
#
# Scope: the DISPLAYED lane only (`placement: block`, plus the raw centered
# vignettes below). `placement: wrap` is deliberately untouched — a wrap has prose
# beside it rather than above and below it, its space is \intextsep/\columnsep, and
# the wrapped vignette on folio 198 reads correctly today. Full-page plates are out
# of scope by Luis's own framing and are excluded structurally (see
# _RAW_CENTERED_VIGNETTE_RE).
_BLOCK_IMAGE_GAP_DEFAULT = "2\\baselineskip"

# Content-margin detection. A pixel counts as ink when compositing it onto white
# paper darkens the paper by more than _AUTO_TRIM_INK_FLOOR/255 (~8%); below that
# it does not print as anything a reader can see. A row/column counts as content
# when at least _AUTO_TRIM_LINE_COVERAGE of it is ink, which keeps stray specks and
# scan noise from defeating the crop.
_AUTO_TRIM_INK_FLOOR = 20
_AUTO_TRIM_LINE_COVERAGE = 0.005
# Margins under 4% are hairlines. With the 2% bleed below, this means a crop only
# ever happens when it removes at least 2% of a dimension — enough to matter on the
# page, and never enough churn to produce a trimmed twin for a rounding error.
_AUTO_TRIM_MIN_MARGIN = 0.04
# Give back 2% of the natural dimension as bleed so a hard clip never lands on the
# still-visible part of a vignette's fade.
_AUTO_TRIM_BLEED = 0.02
# Refuse to remove more than 45% from any one edge: past that the measurement is
# more likely wrong than the asset is.
_AUTO_TRIM_MAX_EDGE = 0.45
_AUTO_TRIM_PLACEMENTS = {"block"}

# Raw `\begin{center}\includegraphics[width=<absolute>]{path}\end{center}` written
# directly into source, which is how two object vignettes (both
# named in the folio-168 note), the blueberry hill, the birches and a
# third vignette are wired. These never passed through `of-image`, so an
# of-image-only fix would have missed exactly the instances Luis cited. Normalizing
# them in the render-only copy fixes them without touching book source.
#
# The guard is deliberately narrow so full-page plates cannot be caught: it demands
# a line-initial match (so a quoted/commented placement directive is skipped), a
# lone `width=` key in an ABSOLUTE unit, and a brace-free literal path. Every
# full-page plate in the book carries `width=\textwidth,height=0.9\textheight,
# keepaspectratio` and a `\detokenize{...}` path, and so fails all three.
_RAW_CENTERED_VIGNETTE_RE = re.compile(
    r"^\\begin\{center\}[ \t]*"
    r"\\includegraphics\[[ \t]*width[ \t]*=[ \t]*"
    r"(?P<width>(?:0?\.\d+|[1-9]\d*(?:\.\d+)?)(?:in|cm|mm|pt))[ \t]*\]"
    r"\{(?P<path>[^{}\\%#$`\s]+)\}[ \t]*"
    r"\\end\{center\}[ \t]*$",
    re.MULTILINE,
)

_DIMENSION_PARTS_RE = re.compile(
    r"^(?P<coeff>(?:0(?:\.0+)?|0?\.\d+|[1-9]\d*(?:\.\d+)?))?"
    r"(?P<unit>\\[a-z]+|in|cm|mm|pt|em|ex)$"
)
_IMAGE_INITIAL_RECIPES: dict[str, dict[str, Any]] = {
    "codex0_a5_default": {
        "width": ".72in",
        "lines": 4,
        "gap": ".06in",
        "raise": "0in",
        "align": "bottom",
    },
    "mythic_letter_default": {
        "width": ".84in",
        "lines": 4,
        "gap": ".08in",
        "raise": "0in",
        "align": "bottom",
    },
    "cam_letter_default": {
        "width": ".80in",
        "lines": 4,
        "gap": ".08in",
        "raise": "0in",
        "align": "bottom",
    },
    "generic_report_default": {
        "width": ".78in",
        "lines": 4,
        "gap": ".08in",
        "raise": "0in",
        "align": "bottom",
    },
}
_LATEX_TEXT_REPLACEMENTS = {
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


_LAYOUT_IMAGE_HEADER_INCLUDES = [
    r"\usepackage{graphicx}",
    r"\usepackage{wrapfig}",
    r"\usepackage{tikz}",
    r"\usetikzlibrary{calc}",
    # tikzpagenodes supplies `current page text area`, which plain TikZ does not.
    # codex0.tex's \OFCompassField anchors the handwritten-ask compass field to the
    # text block rather than the sheet, so without this the build dies with
    # "No shape named `current page text area' is known" (verified 2026-08-11).
    r"\usepackage{tikzpagenodes}",
    r"\usepackage{eso-pic}",
    r"\providecommand{\OFDecorativeImage}[3]{\begingroup\def\OFEdgeMode{#3}\begin{tikzpicture}\node[inner sep=0pt,outer sep=0pt] (ofimg) {\includegraphics[#1]{#2}};\ifx\OFEdgeMode\empty\else\begin{scope}\clip (ofimg.south west) rectangle (ofimg.north east);\draw[white,line width=10pt,opacity=0.55] (ofimg.south west) rectangle (ofimg.north east);\draw[white,line width=22pt,opacity=0.22] (ofimg.south west) rectangle (ofimg.north east);\end{scope}\fi\end{tikzpicture}\endgroup}",
    r"\newlength{\OFWrapSavedColumnSep}",
    r"\newlength{\OFWrapSavedInTextSep}",
    # Displayed-image envelope. Geometry is character-for-character the hinge
    # ornament's (\CodexBreakOrnament in codex0.tex): rigid \vspace, a centered
    # group, rigid \vspace. Bare `\begin{center}` is not used because its trivlist
    # skips are both smaller than a hinge and stretchy. Defined defensively so a
    # template that already provides the environment wins.
    # NB: \newenvironment may only reference #1 in its BEGIN code — LaTeX gives
    # "Illegal parameter number in definition of \end<env>" otherwise (it broke
    # build 65). The gap is stashed in a macro at \begin time, outside the
    # centering group so it survives into the end code, and read back there.
    r"\makeatletter\@ifundefined{OFDisplayedFigure}{\newenvironment{OFDisplayedFigure}[1][2\baselineskip]{\par\def\OFDisplayedFigureGap{#1}\vspace{\OFDisplayedFigureGap}\begingroup\centering}{\par\endgroup\vspace{\OFDisplayedFigureGap}}}{}\makeatother",
]
_IMAGE_INITIAL_HEADER_INCLUDES = [
    r"\usepackage{yugenillumination}",
]


def preprocess_layout_image_blocks(
    source: Path,
    output_dir: Path,
    render_id: str,
    graphicspath_extra_roots: list[Path] | None = None,
    *,
    force_graphicspath: bool = False,
) -> LayoutImagePreprocessResult:
    """Rewrite fenced `of-image` blocks into render-only raw LaTeX.

    The original source is never mutated. The returned source path is the original
    path when the source has neither Foundry image blocks nor raw LaTeX image
    controls. Raw supported image macros receive the supplied ``\\graphicspath``
    ordering. ``force_graphicspath`` lets manifest-backed PDF renders propagate
    their effective roots for template resources even when the body has no image
    controls, without changing the default image-free no-op.
    """

    if not source.exists():
        return LayoutImagePreprocessResult(changed=False, rewritten_source=source)

    text = source.read_text(encoding="utf-8", errors="ignore")
    image_matches = list(_BLOCK_RE.finditer(text))
    initial_matches = list(_INITIAL_BLOCK_RE.finditer(text))
    raw_latex_resources = _RAW_LATEX_RESOURCE_RE.search(text) is not None
    if not image_matches and not initial_matches and not raw_latex_resources and not force_graphicspath:
        return LayoutImagePreprocessResult(changed=False, rewritten_source=source)

    output_dir.mkdir(parents=True, exist_ok=True)
    inventory: list[dict[str, Any]] = []
    used_layout_images = False
    used_image_initials = False
    # Resolved before the substitutions now, because auto-trim has to find the
    # asset on disk to measure the whitespace it ships. Output dir is one of the
    # roots, so a trimmed twin written there needs no extra graphicspath entry.
    graphicspath_roots = _graphicspath_roots(source, output_dir, graphicspath_extra_roots or [])

    def resolve_asset(reference: str) -> Path | None:
        return _resolve_asset_path(reference, graphicspath_roots)

    def replace_block(match: re.Match[str]) -> str:
        nonlocal used_layout_images
        used_layout_images = True
        idx = len(inventory) + 1
        cfg = _parse_block_yaml(match.group("body"), idx)
        _apply_auto_trim(cfg, resolve_asset, output_dir)
        latex = _render_layout_image_latex(cfg)
        inventory.append(_inventory_entry(cfg, idx))
        return latex

    def replace_raw_centered_vignette(match: re.Match[str]) -> str:
        nonlocal used_layout_images
        cfg = _raw_centered_vignette_cfg(match)
        if cfg is None:
            return match.group(0)
        used_layout_images = True
        idx = len(inventory) + 1
        _apply_auto_trim(cfg, resolve_asset, output_dir)
        latex = _render_layout_image_latex(cfg)
        inventory.append(_inventory_entry(cfg, idx))
        return latex

    def replace_initial_block(match: re.Match[str]) -> str:
        nonlocal used_image_initials
        used_image_initials = True
        idx = len(inventory) + 1
        cfg = _parse_initial_yaml(match.group("body"), idx)
        latex = _render_image_initial_latex(cfg)
        inventory.append(_initial_inventory_entry(cfg, idx))
        return latex

    rewritten_body = _BLOCK_RE.sub(replace_block, text)
    rewritten_body = _INITIAL_BLOCK_RE.sub(replace_initial_block, rewritten_body)
    # After the of-image pass, so the envelope this emits is never re-matched.
    rewritten_body = _RAW_CENTERED_VIGNETTE_RE.sub(replace_raw_centered_vignette, rewritten_body)
    include_lines: list[str] = []
    if used_layout_images:
        include_lines.extend(_LAYOUT_IMAGE_HEADER_INCLUDES)
    if used_image_initials:
        include_lines.extend(_IMAGE_INITIAL_HEADER_INCLUDES)
    include_lines.append(_graphicspath_include(graphicspath_roots))
    rewritten = _ensure_header_includes(rewritten_body, include_lines)
    out_path = output_dir / f"{render_id}.layout_images.md"
    out_path.write_text(rewritten, encoding="utf-8")
    return LayoutImagePreprocessResult(
        changed=True,
        rewritten_source=out_path,
        figure_inventory=inventory,
        graphicspath_roots=graphicspath_roots,
    )


def _parse_block_yaml(raw: str, idx: int) -> dict[str, Any]:
    try:
        import yaml
        data = yaml.safe_load(raw) or {}
    except Exception as exc:
        raise LayoutImageRenderError(f"of-image[{idx}] YAML parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise LayoutImageRenderError(f"of-image[{idx}] must contain a YAML mapping")

    path = data.get("path") or data.get("src") or data.get("image")
    if not _safe_resource_path(path):
        raise LayoutImageRenderError(f"of-image[{idx}] path must be a relative image/PDF path inside render resource roots")

    placement = str(data.get("placement", "inline")).strip().lower().replace("_", "-")
    if placement not in _ALLOWED_PLACEMENTS:
        raise LayoutImageRenderError(f"of-image[{idx}] placement must be one of: {', '.join(sorted(_ALLOWED_PLACEMENTS))}")

    align = str(data.get("align", data.get("side", "right"))).strip().lower()
    if align not in _ALLOWED_ALIGN:
        raise LayoutImageRenderError(f"of-image[{idx}] align must be left or right")

    width = _safe_dimension(data.get("width"), default="0.32\\textwidth")
    image_width = _safe_dimension(data.get("image_width"), default="\\linewidth" if placement == "wrap" else width)
    if width.startswith("-") or image_width.startswith("-"):
        raise LayoutImageRenderError(f"of-image[{idx}] width values must be positive dimensions")
    wrapped_lines = _safe_optional_int(
        data.get("lines", data.get("wrapped_lines")),
        idx=idx,
        label="lines",
        minimum=1,
        maximum=40,
    )
    overhang = _safe_optional_dimension(data.get("overhang"), idx=idx, label="overhang")
    sep = _safe_optional_dimension(data.get("sep", data.get("columnsep")), idx=idx, label="sep")
    intextsep = _safe_optional_dimension(data.get("intextsep", data.get("in_text_sep")), idx=idx, label="intextsep")
    raise_amount = _safe_optional_dimension(data.get("raise", data.get("vertical_raise")), idx=idx, label="raise")
    # `gap` is the displayed-image envelope (block placement only). Default is the
    # hinge ornament's own gap so an image reads as a hinge does; a passage that
    # genuinely wants a different weight can say so.
    gap = _safe_optional_dimension(data.get("gap", data.get("block_gap")), idx=idx, label="gap")
    trim = _safe_trim(data.get("trim"), idx=idx)
    clip = _safe_bool(data.get("clip"), default=False, idx=idx, label="clip")
    # An author-supplied trim is a deliberate crop and always wins over the
    # measured one; `auto_trim: false` opts out entirely.
    auto_trim = _safe_bool(data.get("auto_trim", data.get("auto-trim")), default=True, idx=idx, label="auto_trim")
    x_offset = _safe_dimension(data.get("x", data.get("x_offset")), default="0in")
    y_offset = _safe_dimension(data.get("y", data.get("y_offset")), default="0in")
    anchor = str(data.get("anchor", "north east")).strip().lower().replace("_", " ").replace("-", " ")
    if anchor not in _ALLOWED_ANCHORS:
        raise LayoutImageRenderError(f"of-image[{idx}] anchor must be one of: {', '.join(sorted(_ALLOWED_ANCHORS))}")

    opacity = str(data.get("opacity", "1")).strip()
    if not _SAFE_OPACITY_RE.match(opacity):
        raise LayoutImageRenderError(f"of-image[{idx}] opacity must be a number from 0 to 1")

    edge = str(data.get("edge", data.get("edges", "none"))).strip().lower()
    if edge not in _ALLOWED_EDGES:
        raise LayoutImageRenderError(f"of-image[{idx}] edge must be none, fade, vignette, soft, or soft-edge")
    edge = "" if edge in {"", "none"} else ("soft" if edge in {"soft-edge", "soft_edge"} else edge)

    caption = data.get("caption", "")
    if caption is not None and not isinstance(caption, (str, int, float)):
        raise LayoutImageRenderError(f"of-image[{idx}] caption must be scalar text")

    return {
        "path": str(path),
        "placement": placement,
        "align": align,
        "align_code": _ALLOWED_ALIGN[align],
        "width": width,
        "image_width": image_width,
        "wrapped_lines": wrapped_lines,
        "overhang": overhang,
        "sep": sep,
        "intextsep": intextsep,
        "raise": raise_amount,
        "gap": gap,
        "auto_trim": auto_trim,
        "trim": trim,
        "clip": clip,
        "x": x_offset,
        "y": y_offset,
        "anchor": anchor,
        "opacity": opacity,
        "edge": edge,
        "caption": "" if caption is None else str(caption),
    }


def image_initial_recipes() -> dict[str, dict[str, Any]]:
    """Return the named `of-initial` tuning recipes available to source authors."""
    return {name: dict(values) for name, values in _IMAGE_INITIAL_RECIPES.items()}


def _parse_initial_yaml(raw: str, idx: int) -> dict[str, Any]:
    try:
        import yaml
        data = yaml.safe_load(raw) or {}
    except Exception as exc:
        raise LayoutImageRenderError(f"of-initial[{idx}] YAML parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise LayoutImageRenderError(f"of-initial[{idx}] must contain a YAML mapping")

    recipe_name = data.get("recipe")
    recipe: dict[str, Any] = {}
    if recipe_name is not None:
        if not isinstance(recipe_name, str) or recipe_name not in _IMAGE_INITIAL_RECIPES:
            raise LayoutImageRenderError(
                f"of-initial[{idx}] unknown recipe: {recipe_name}. Available recipes: {', '.join(sorted(_IMAGE_INITIAL_RECIPES))}"
            )
        recipe = _IMAGE_INITIAL_RECIPES[recipe_name]

    path = data.get("path") or data.get("src") or data.get("image")
    if not _safe_resource_path(path):
        raise LayoutImageRenderError(f"of-initial[{idx}] path must be a relative image/PDF path inside render resource roots")

    width = _safe_dimension(data.get("width", recipe.get("width")), default="0.84in")
    gap = _safe_dimension(data.get("gap", recipe.get("gap")), default="0.08in")
    raise_amount = _safe_dimension(
        data.get("raise", data.get("vertical_raise", recipe.get("raise"))),
        default="0in",
    )
    if width.startswith("-") or gap.startswith("-"):
        raise LayoutImageRenderError(f"of-initial[{idx}] width and gap must be positive dimensions")

    try:
        wrapped_lines = int(data.get("lines", data.get("wrapped_lines", recipe.get("lines", 4))))
    except (TypeError, ValueError) as exc:
        raise LayoutImageRenderError(f"of-initial[{idx}] lines must be an integer") from exc
    if wrapped_lines < 1 or wrapped_lines > 12:
        raise LayoutImageRenderError(f"of-initial[{idx}] lines must be between 1 and 12")

    alignment = str(
        data.get("align", data.get("alignment", recipe.get("align", "bottom")))
    ).strip().lower().replace("_", "-")
    if alignment not in _ALLOWED_INITIAL_ALIGNMENTS:
        raise LayoutImageRenderError(f"of-initial[{idx}] align must be bottom or top")

    return {
        "path": str(path),
        "width": width,
        "gap": gap,
        "raise": raise_amount,
        "wrapped_lines": wrapped_lines,
        "alignment": alignment,
        "recipe": recipe_name,
    }


def _raw_centered_vignette_cfg(match: re.Match[str]) -> dict[str, Any] | None:
    """Build a displayed-image config from a raw centered `\\includegraphics` line.

    Returns None when the path is not a raster the trimmer can reason about, in
    which case the caller leaves the source line exactly as written.
    """

    path = match.group("path")
    if Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        return None
    return {
        "path": path,
        "placement": "block",
        "align": "right",
        "align_code": "r",
        "width": match.group("width"),
        "image_width": match.group("width"),
        "wrapped_lines": None,
        "overhang": None,
        "sep": None,
        "intextsep": None,
        "raise": None,
        "gap": None,
        "auto_trim": True,
        "trim": None,
        "clip": False,
        "x": "0in",
        "y": "0in",
        "anchor": "north east",
        "opacity": "1",
        "edge": "",
        "caption": "",
        "origin": "raw_centered_graphic",
    }


def _resolve_asset_path(reference: str, graphicspath_roots: list[str]) -> Path | None:
    """Locate an image on disk the way LaTeX's \\graphicspath will locate it."""

    candidate = Path(reference)
    try:
        if candidate.is_absolute():
            return candidate if candidate.is_file() else None
        for root in graphicspath_roots:
            probe = Path(root) / candidate
            if probe.is_file():
                return probe
    except OSError:
        return None
    return None


def _content_margins(path: Path) -> tuple[float, float, float, float] | None:
    """Measure the blank margin an image ships inside its own canvas.

    Returns (left, bottom, right, top) as fractions of the natural size, in
    graphicx's `trim` order. Returns None whenever the margin cannot be measured —
    no Pillow, unreadable file, vector art, all-blank canvas. Fail-open is
    deliberate: an unmeasurable asset keeps exactly the placement it has today.
    """

    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(path) as handle:
            image = handle.convert("RGBA")
    except Exception:
        return None
    width, height = image.size
    if width < 8 or height < 8:
        return None
    try:
        # Judge the asset the way the page will: composited onto paper white, since
        # a low-alpha wash and a pale wash read identically once printed.
        paper = Image.new("RGBA", image.size, (255, 255, 255, 255))
        flat = Image.alpha_composite(paper, image).convert("L")
        ceiling = 255 - _AUTO_TRIM_INK_FLOOR
        ink = flat.point(lambda value: 255 if value <= ceiling else 0)
        # A BOX resize to one pixel wide/tall is a per-row / per-column mean.
        row_means = ink.resize((1, height), Image.BOX).tobytes()
        column_means = ink.resize((width, 1), Image.BOX).tobytes()
    except Exception:
        return None
    floor = _AUTO_TRIM_LINE_COVERAGE * 255
    rows = [index for index, value in enumerate(row_means) if value >= floor]
    columns = [index for index, value in enumerate(column_means) if value >= floor]
    if not rows or not columns:
        return None
    return (
        columns[0] / width,
        (height - 1 - rows[-1]) / height,
        (width - 1 - columns[-1]) / width,
        rows[0] / height,
    )


def _auto_trim_plan(margins: tuple[float, float, float, float]) -> tuple[float, float, float, float] | None:
    """Turn measured margins into a crop, or None when cropping is not warranted."""

    plan = []
    for margin in margins:
        cut = 0.0 if margin < _AUTO_TRIM_MIN_MARGIN else margin - _AUTO_TRIM_BLEED
        plan.append(min(max(cut, 0.0), _AUTO_TRIM_MAX_EDGE))
    left, bottom, right, top = plan
    if not any(plan):
        return None
    if left + right >= 0.9 or top + bottom >= 0.9:
        return None
    return (left, bottom, right, top)


def _write_trimmed_asset(source_image: Path, plan: tuple[float, float, float, float], output_dir: Path) -> Path | None:
    """Write a margin-cropped twin of ``source_image`` into the render output dir.

    The source asset is never touched. The name is content-addressed so repeat
    renders reuse the same file and a re-exported asset gets a fresh one.
    """

    try:
        from PIL import Image
    except Exception:
        return None
    left, bottom, right, top = plan
    try:
        stat = source_image.stat()
        stamp = hashlib.sha256(
            "|".join(
                [str(source_image), str(stat.st_mtime_ns), str(stat.st_size), *(f"{value:.6f}" for value in plan)]
            ).encode("utf-8")
        ).hexdigest()[:12]
        destination = output_dir / f"{_trim_stem(source_image)}__oftrim_{stamp}.png"
        if destination.is_file():
            return destination
        with Image.open(source_image) as handle:
            image = handle.convert("RGBA")
            width, height = image.size
            box = (
                round(left * width),
                round(top * height),
                width - round(right * width),
                height - round(bottom * height),
            )
            if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                return None
            image.crop(box).save(destination)
    except Exception:
        return None
    return destination


def _trim_stem(source_image: Path) -> str:
    """A graphicspath-safe, collision-resistant stem for a trimmed twin."""

    stem = re.sub(r"[^A-Za-z0-9._-]", "-", source_image.stem)
    return stem[:80] or "of-image"


def _scale_dimension(value: str, factor: float) -> str | None:
    """Scale a LaTeX dimension by a plain factor, keeping its unit or macro."""

    match = _DIMENSION_PARTS_RE.match(value)
    if not match:
        return None
    coefficient = float(match.group("coeff") or "1")
    scaled = coefficient * factor
    text = f"{scaled:.4f}".rstrip("0").rstrip(".")
    if not text or text == "0":
        return None
    candidate = f"{text}{match.group('unit')}"
    return candidate if _SAFE_DIMENSION_RE.match(candidate) else None


def _apply_auto_trim(cfg: dict[str, Any], resolve: Any, output_dir: Path) -> None:
    """Crop the whitespace a displayed image ships inside its own canvas.

    Mutates ``cfg`` in place to point at a trimmed twin and to shrink the declared
    width by the retained fraction, so the visible object keeps the size it has
    today and only the surrounding air changes. Every failure path is a no-op.
    """

    cfg.setdefault("auto_trim", True)
    cfg["auto_trim_applied"] = None
    if not cfg.get("auto_trim") or cfg.get("trim"):
        return
    if cfg.get("placement") not in _AUTO_TRIM_PLACEMENTS:
        return
    resolved = resolve(cfg["path"])
    if resolved is None:
        return
    margins = _content_margins(resolved)
    if margins is None:
        return
    plan = _auto_trim_plan(margins)
    if plan is None:
        return
    retained_width = 1.0 - plan[0] - plan[2]
    scaled_width = _scale_dimension(cfg["width"], retained_width)
    if scaled_width is None:
        return
    trimmed = _write_trimmed_asset(resolved, plan, output_dir)
    if trimmed is None:
        return
    cfg["auto_trim_applied"] = {
        # The inventory keeps pointing at the authored reference — it audits what
        # the source asked for, and it feeds resource-root resolution, which knows
        # nothing about render-local derivatives. The twin is recorded here.
        "authored_path": cfg["path"],
        "source": str(resolved),
        "trimmed": trimmed.name,
        "authored_width": cfg["width"],
        "margins": [round(value, 4) for value in margins],
        "removed": [round(value, 4) for value in plan],
        "retained_width": round(retained_width, 4),
    }
    cfg["path"] = trimmed.name
    cfg["width"] = scaled_width
    cfg["image_width"] = scaled_width


def _safe_resource_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "://" in value:
        return False
    if any(ord(ch) < 32 for ch in value):
        return False
    if any(ch in value for ch in ("\\", "{", "}", "$", "`", "%", "#")):
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    return path.suffix.lower() in _IMAGE_EXTENSIONS


def _safe_dimension(value: Any, default: str) -> str:
    if value is None or value == "":
        return default
    text = str(value).strip()
    if not _SAFE_DIMENSION_RE.match(text):
        raise LayoutImageRenderError(f"unsafe dimension value: {text}")
    return text


def _safe_optional_dimension(value: Any, *, idx: int, label: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        return _safe_dimension(value, default="0in")
    except LayoutImageRenderError as exc:
        raise LayoutImageRenderError(f"of-image[{idx}] unsafe {label} dimension: {value}") from exc


def _safe_optional_int(value: Any, *, idx: int, label: str, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise LayoutImageRenderError(f"of-image[{idx}] {label} must be an integer from {minimum} to {maximum}") from exc
    if number < minimum or number > maximum:
        raise LayoutImageRenderError(f"of-image[{idx}] {label} must be an integer from {minimum} to {maximum}")
    return number


def _safe_bool(value: Any, *, default: bool, idx: int, label: str) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off"}:
        return False
    raise LayoutImageRenderError(f"of-image[{idx}] {label} must be true or false")


def _safe_trim(value: Any, *, idx: int) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value]
    else:
        parts = str(value).strip().split()
    if len(parts) != 4:
        raise LayoutImageRenderError(f"of-image[{idx}] trim must contain four safe dimensions")
    for part in parts:
        _safe_dimension(part, default="0pt")
    return " ".join(parts)


def _latex_escape_text(value: str) -> str:
    return "".join(_LATEX_TEXT_REPLACEMENTS.get(ch, ch) for ch in value)


def _graphicspath_roots(source: Path, output_dir: Path, extra_roots: list[Path] | None = None) -> list[str]:
    """Return absolute image search roots for raw LaTeX layout images.

    Pandoc's `--resource-path` does not help raw `\\includegraphics` emitted by
    the layout-image preprocessor. Add the canonical/staged source directory so
    `path: assets/foo.png` resolves relative to the authored source, and add the
    render output directory for generated render-local assets. Dedupe while
    preserving order.
    """

    roots: list[str] = []
    # Callers that supply a complete effective chain own precedence. The source
    # and output roots remain appended compatibility fallbacks for direct calls.
    for path in (*(extra_roots or []), source.parent, output_dir):
        resolved = path.resolve()
        text = resolved.as_posix().rstrip("/") + "/"
        if not _safe_graphicspath_root(text):
            raise LayoutImageRenderError(
                "of-image cannot add this source/output directory to LaTeX \\graphicspath because "
                f"the filesystem path contains TeX-unsafe characters: {text}. "
                "Move the source/render output to a path without %, #, $, braces, backticks, "
                "backslashes, URL syntax, or control characters, then render again."
            )
        if text not in roots:
            roots.append(text)
    return roots


def _safe_graphicspath_root(value: str) -> bool:
    if not value.startswith("/") or "://" in value:
        return False
    if any(ord(ch) < 32 for ch in value):
        return False
    return not any(ch in value for ch in ("\\", "{", "}", "$", "`", "%", "#"))


def _graphicspath_include(roots: list[str]) -> str:
    joined = "".join(f"{{{root}}}" for root in roots)
    return f"\\graphicspath{{{joined}}}"


def _render_layout_image_latex(cfg: dict[str, Any]) -> str:
    placement = cfg["placement"]
    if placement == "wrap":
        begin = "\\begin{wrapfigure}"
        if cfg.get("wrapped_lines") is not None:
            begin += f"[{cfg['wrapped_lines']}]"
        begin += f"{{{cfg['align_code']}}}"
        if cfg.get("overhang") is not None:
            begin += f"[{cfg['overhang']}]"
        begin += f"{{{cfg['width']}}}"
        image_options = [f"width={cfg['image_width']}"]
        if cfg.get("trim"):
            image_options.append(f"trim={cfg['trim']}")
        if cfg.get("clip"):
            image_options.append("clip")
        lines = [
            *(["\\setlength{\\OFWrapSavedColumnSep}{\\columnsep}", f"\\setlength{{\\columnsep}}{{{cfg['sep']}}}"] if cfg.get("sep") else []),
            *(["\\setlength{\\OFWrapSavedInTextSep}{\\intextsep}", f"\\setlength{{\\intextsep}}{{{cfg['intextsep']}}}"] if cfg.get("intextsep") else []),
            *([f"\\vspace*{{{cfg['raise']}}}"] if cfg.get("raise") else []),
            begin,
            "\\centering",
            f"\\OFDecorativeImage{{{','.join(image_options)}}}{{{cfg['path']}}}{{{cfg['edge']}}}",
        ]
        if cfg["caption"]:
            lines.append(f"\\caption{{{_latex_escape_text(cfg['caption'])}}}")
        lines.append("\\end{wrapfigure}")
        if cfg.get("sep"):
            lines.append("\\setlength{\\columnsep}{\\OFWrapSavedColumnSep}")
        if cfg.get("intextsep"):
            lines.append("\\setlength{\\intextsep}{\\OFWrapSavedInTextSep}")
        return "\n".join(lines)

    if placement == "absolute":
        anchor = cfg["anchor"]
        return "\n".join(
            [
                "\\AddToShipoutPictureFG*{%",
                "  \\begin{tikzpicture}[remember picture,overlay]",
                f"    \\node[anchor={anchor},opacity={cfg['opacity']}] at ([xshift={cfg['x']},yshift={cfg['y']}]current page.{anchor}) "
                f"{{\\OFDecorativeImage{{width={cfg['width']}}}{{{cfg['path']}}}{{{cfg['edge']}}}}};",
                "  \\end{tikzpicture}%",
                "}",
            ]
        )

    if placement == "inline":
        return f"\\OFDecorativeImage{{width={cfg['width']}}}{{{cfg['path']}}}{{{cfg['edge']}}}"

    # `block` is flow-preserving but displayed/centered. The envelope is the hinge
    # ornament's, so a displayed image sits in the page at the weight Luis ruled on
    # folio 168 rather than at LaTeX's trivlist default.
    gap = cfg.get("gap") or _BLOCK_IMAGE_GAP_DEFAULT
    lines = [
        f"\\begin{{OFDisplayedFigure}}[{gap}]",
        f"\\OFDecorativeImage{{width={cfg['width']}}}{{{cfg['path']}}}{{{cfg['edge']}}}",
    ]
    if cfg["caption"]:
        lines.append(f"\\emph{{{_latex_escape_text(cfg['caption'])}}}")
    lines.append("\\end{OFDisplayedFigure}")
    return "\n".join(lines)


def _render_image_initial_latex(cfg: dict[str, Any]) -> str:
    return (
        f"\\OFImageInitialSetup{{{cfg['path']}}}{{{cfg['width']}}}"
        f"{{{cfg['wrapped_lines']}}}{{{cfg['gap']}}}{{{cfg['raise']}}}{{{cfg['alignment']}}} "
    )


def _inventory_entry(cfg: dict[str, Any], idx: int) -> dict[str, Any]:
    auto_trim = cfg.get("auto_trim_applied")
    return {
        "kind": "layout_image",
        "index": idx,
        "path": (auto_trim or {}).get("authored_path", cfg["path"]),
        "placement": cfg["placement"],
        "align": cfg["align"],
        "width": cfg["width"],
        "edge": cfg["edge"] or "none",
        "image_width": cfg.get("image_width"),
        "wrapped_lines": cfg.get("wrapped_lines"),
        "overhang": cfg.get("overhang"),
        "sep": cfg.get("sep"),
        "intextsep": cfg.get("intextsep"),
        "raise": cfg.get("raise"),
        "gap": cfg.get("gap") or (_BLOCK_IMAGE_GAP_DEFAULT if cfg["placement"] == "block" else None),
        "trim": cfg.get("trim"),
        "clip": cfg.get("clip", False),
        "origin": cfg.get("origin", "of_image_block"),
        "auto_trim": auto_trim,
    }


def _initial_inventory_entry(cfg: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "kind": "image_initial",
        "index": idx,
        "path": cfg["path"],
        "width": cfg["width"],
        "gap": cfg["gap"],
        "wrapped_lines": cfg["wrapped_lines"],
        "alignment": cfg["alignment"],
        "raise": cfg["raise"],
        "recipe": cfg.get("recipe"),
    }


def _ensure_header_includes(text: str, include_lines: list[str]) -> str:
    frontmatter, body, had_frontmatter = _split_frontmatter(text)
    includes = frontmatter.get("header-includes") or frontmatter.get("header_includes")
    if includes is None:
        frontmatter["header-includes"] = list(include_lines)
    elif isinstance(includes, list):
        frontmatter["header-includes"] = [*includes, *include_lines]
    else:
        frontmatter["header-includes"] = [includes, *include_lines]
        frontmatter.pop("header_includes", None)

    try:
        import yaml
        fm_yaml = yaml.safe_dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False).rstrip()
    except Exception:
        fm_yaml = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
    separator = "" if body.startswith("\n") else "\n"
    return f"---\n{fm_yaml}\n---{separator}{body}" if had_frontmatter else f"---\n{fm_yaml}\n---\n\n{body}"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str, bool]:
    stripped = text.lstrip()
    leading = text[: len(text) - len(stripped)]
    if not stripped.startswith("---"):
        return {}, text, False
    end = stripped.find("\n---", 3)
    if end == -1:
        return {}, text, False
    frontmatter_raw = stripped[3:end]
    body = stripped[end + 4 :]
    try:
        import yaml
        frontmatter = yaml.safe_load(frontmatter_raw) or {}
    except Exception:
        return {}, text, False
    if not isinstance(frontmatter, dict):
        return {}, text, False
    return frontmatter, leading + body, True
