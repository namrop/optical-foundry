"""Preprocess Optical Foundry layout-image source blocks.

The source-facing surface is an explicit fenced block, not default Markdown image
behavior:

```of-image
path: assets/portrait.png
placement: wrap        # wrap | absolute | inline
align: right           # wrap only: left | right
width: 0.34\textwidth
edge: vignette         # none | fade | vignette | soft
caption: Optional caption
```

The preprocessor rewrites the block into guarded raw LaTeX. It is intentionally
PDF/LaTeX-oriented: Markdown remains the canonical source surface, while the
render-only copy carries wrapfig/TikZ/eso-pic commands for Pandoc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re


class LayoutImageRenderError(RuntimeError):
    """Raised when an `of-image` block is unsafe or malformed."""


@dataclass(frozen=True)
class LayoutImagePreprocessResult:
    changed: bool
    rewritten_source: Path
    figure_inventory: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_BLOCK_RE = re.compile(r"^```of-image\s*\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL)
_SAFE_DIMENSION_RE = re.compile(
    r"^-?(?:\\(?:linewidth|textwidth|textheight|paperwidth|paperheight)|(?:0?\.\d+|[1-9]\d*(?:\.\d+)?)(?:\\(?:linewidth|textwidth|textheight|paperwidth|paperheight)|in|cm|mm|pt|em|ex))$"
)
_SAFE_OPACITY_RE = re.compile(r"^(?:0(?:\.\d+)?|1(?:\.0+)?)$")
_ALLOWED_PLACEMENTS = {"wrap", "absolute", "inline", "block"}
_ALLOWED_ALIGN = {"left": "l", "right": "r"}
_ALLOWED_ANCHORS = {"north east", "north west", "south east", "south west", "center"}
_ALLOWED_EDGES = {"", "none", "fade", "vignette", "soft", "soft-edge", "soft_edge"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
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
    r"\IfFileExists{wrapfig.sty}{\usepackage{wrapfig}}{\newenvironment{wrapfigure}[2]{\par\begin{figure}[htbp]\centering}{\end{figure}\par}}",
    r"\usepackage{tikz}",
    r"\usetikzlibrary{calc}",
    r"\usepackage{eso-pic}",
    r"\providecommand{\OFDecorativeImage}[3]{\begingroup\def\OFEdgeMode{#3}\begin{tikzpicture}\node[inner sep=0pt,outer sep=0pt] (ofimg) {\includegraphics[#1]{#2}};\ifx\OFEdgeMode\empty\else\begin{scope}\clip (ofimg.south west) rectangle (ofimg.north east);\draw[white,line width=10pt,opacity=0.55] (ofimg.south west) rectangle (ofimg.north east);\draw[white,line width=22pt,opacity=0.22] (ofimg.south west) rectangle (ofimg.north east);\end{scope}\fi\end{tikzpicture}\endgroup}",
]


def preprocess_layout_image_blocks(source: Path, output_dir: Path, render_id: str) -> LayoutImagePreprocessResult:
    """Rewrite fenced `of-image` blocks into render-only raw LaTeX.

    The original source is never mutated. The returned source path is either the
    original path (when no blocks are present) or a generated Markdown copy under
    `output_dir`.
    """

    if not source.exists():
        return LayoutImagePreprocessResult(changed=False, rewritten_source=source)

    text = source.read_text(encoding="utf-8", errors="ignore")
    matches = list(_BLOCK_RE.finditer(text))
    if not matches:
        return LayoutImagePreprocessResult(changed=False, rewritten_source=source)

    output_dir.mkdir(parents=True, exist_ok=True)
    inventory: list[dict[str, Any]] = []

    def replace_block(match: re.Match[str]) -> str:
        idx = len(inventory) + 1
        cfg = _parse_block_yaml(match.group("body"), idx)
        latex = _render_layout_image_latex(cfg)
        inventory.append(_inventory_entry(cfg, idx))
        return latex

    rewritten_body = _BLOCK_RE.sub(replace_block, text)
    rewritten = _ensure_header_includes(rewritten_body, _LAYOUT_IMAGE_HEADER_INCLUDES)
    out_path = output_dir / f"{render_id}.layout_images.md"
    out_path.write_text(rewritten, encoding="utf-8")
    return LayoutImagePreprocessResult(changed=True, rewritten_source=out_path, figure_inventory=inventory)


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
        "x": x_offset,
        "y": y_offset,
        "anchor": anchor,
        "opacity": opacity,
        "edge": edge,
        "caption": "" if caption is None else str(caption),
    }


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


def _latex_escape_text(value: str) -> str:
    return "".join(_LATEX_TEXT_REPLACEMENTS.get(ch, ch) for ch in value)


def _render_layout_image_latex(cfg: dict[str, Any]) -> str:
    placement = cfg["placement"]
    if placement == "wrap":
        lines = [
            f"\\begin{{wrapfigure}}{{{cfg['align_code']}}}{{{cfg['width']}}}",
            "\\centering",
            f"\\OFDecorativeImage{{width={cfg['image_width']}}}{{{cfg['path']}}}{{{cfg['edge']}}}",
        ]
        if cfg["caption"]:
            lines.append(f"\\caption{{{_latex_escape_text(cfg['caption'])}}}")
        lines.append("\\end{wrapfigure}")
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

    # `block` is flow-preserving but displayed/centered.
    lines = [
        "\\begin{center}",
        f"\\OFDecorativeImage{{width={cfg['width']}}}{{{cfg['path']}}}{{{cfg['edge']}}}",
    ]
    if cfg["caption"]:
        lines.append(f"\\emph{{{_latex_escape_text(cfg['caption'])}}}")
    lines.append("\\end{center}")
    return "\n".join(lines)


def _inventory_entry(cfg: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "kind": "layout_image",
        "index": idx,
        "path": cfg["path"],
        "placement": cfg["placement"],
        "align": cfg["align"],
        "width": cfg["width"],
        "edge": cfg["edge"] or "none",
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
