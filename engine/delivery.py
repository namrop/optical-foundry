"""Manifest-owned delivery-mode normalization for physical PDF outputs."""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from engine.page_size import PageMarginError, _normalize_margin_dimension

BOUND_DEFAULT_MARGINS = {
    "inner": "0.85in",
    "outer": "0.60in",
    "top": "0.65in",
    "bottom": "0.70in",
}

SUPPORTED_DELIVERY_MODES = {"screen", "print", "bound", "booklet", "saddle_stitch"}
SUPPORTED_BINDINGS = {"side_staple", "perfect", "saddle_stitch", "coil", "unknown"}
SUPPORTED_PAGE_NUMBER_STRATEGIES = {"outer", "none", "center", "inner", "right"}
SUPPORTED_COLOPHON_PLACEMENTS = {"title_verso", "end"}
ENLARGETHISPAGE_RE = re.compile(r"(?m)^\s*\\enlargethispage\s*\{[^\n{}]*\}\s*\n?")


def normalize_delivery(render_cfg: dict[str, Any], *, scope: str = "render.delivery") -> dict[str, Any]:
    """Return a normalized delivery dict from a manifest render mapping.

    The first implemented physical lane is ``mode: bound``. Non-bound/missing
    delivery keeps a small explicit screen-mode surface so callers can always
    include evidence without inventing profile variants.
    """

    raw = render_cfg.get("delivery") if isinstance(render_cfg, dict) else None
    if raw in (None, ""):
        return {"mode": "screen"}
    if not isinstance(raw, dict):
        raise ValueError(f"{scope} must be a mapping")

    mode = _normalize_token(raw.get("mode", "screen"), default="screen")
    if mode not in SUPPORTED_DELIVERY_MODES:
        raise ValueError(f"{scope}.mode must be one of: {', '.join(sorted(SUPPORTED_DELIVERY_MODES))}")
    if mode in {"booklet", "saddle_stitch"}:
        mode = "bound"
        default_binding = "saddle_stitch"
    else:
        default_binding = "side_staple" if mode == "bound" else "unknown"

    if mode != "bound":
        return {"mode": mode}

    binding = _normalize_token(raw.get("binding", default_binding), default=default_binding)
    if binding not in SUPPORTED_BINDINGS:
        raise ValueError(f"{scope}.binding must be one of: {', '.join(sorted(SUPPORTED_BINDINGS))}")

    duplex = bool(raw.get("duplex", True))
    page_numbers = _normalize_token(raw.get("page_numbers", "outer"), default="outer")
    if page_numbers not in SUPPORTED_PAGE_NUMBER_STRATEGIES:
        raise ValueError(
            f"{scope}.page_numbers must be one of: {', '.join(sorted(SUPPORTED_PAGE_NUMBER_STRATEGIES))}"
        )

    margins = _normalize_delivery_margins(raw.get("margins", {}), scope=f"{scope}.margins")
    colophon = _normalize_colophon(raw.get("colophon", {}), scope=f"{scope}.colophon")
    running_headers = _normalize_running_headers(raw.get("running_headers", {}))
    illumination = _normalize_illumination(raw.get("illumination", {}))

    return {
        "mode": "bound",
        "binding": binding,
        "duplex": duplex,
        "page_numbers": page_numbers,
        "margins": margins,
        "running_headers": running_headers,
        "colophon": colophon,
        "footer_metadata": {"suppress_repeated": bool(raw.get("footer_metadata", {}).get("suppress_repeated", True)) if isinstance(raw.get("footer_metadata", {}), dict) else True},
        "illumination": illumination,
        "signature": {"normalize_to_multiple": 4 if binding == "saddle_stitch" else None},
    }


def validate_delivery(render_cfg: dict[str, Any], *, scope: str = "render.delivery") -> list[str]:
    try:
        normalize_delivery(render_cfg, scope=scope)
    except (ValueError, PageMarginError) as exc:
        return [str(exc)]
    return []


def suppress_bound_pagination_overrides(body: str) -> tuple[str, dict[str, Any]]:
    """Remove source pagination overrides that are unsafe under bound geometry.

    Existing story/proof sources may contain one-off LaTeX page-height tweaks
    tuned for an earlier proof geometry. In a bound duplex output, those commands
    can push live text into the outside page-number lane. Bound mode therefore
    owns this as a delivery concern and suppresses the override while preserving
    surrounding source text.
    """

    stripped, count = ENLARGETHISPAGE_RE.subn("", body)
    evidence = {
        "policy": "suppress_bound_unsafe",
        "enlargethispage_suppressed": count,
        "commands_suppressed": ["enlargethispage"] if count else [],
    }
    return stripped, evidence


def inject_bound_running_header_marks(body: str, *, source: str = "chapter") -> tuple[str, dict[str, Any]]:
    """Insert render-only LaTeX marks for bound running headers.

    Markdown heading conversion does not consistently populate memoir's mark
    registers for unnumbered story headings. When a manifest explicitly enables
    chapter-derived running headers, lower suitable Markdown headings into
    ``\\markboth`` commands without mutating the canonical source.
    """

    normalized_source = _normalize_token(source, default="chapter")
    if normalized_source != "chapter" or "\\markboth" in body:
        return body, {"enabled": True, "source": normalized_source, "marks_inserted": 0}

    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        prefix = match.group("prefix")
        title = match.group("title").strip()
        if not title.lower().startswith("chapter "):
            return match.group(0)
        count += 1
        escaped = _latex_escape(title)
        mark = f"```{{=latex}}\n\\markboth{{{escaped}}}{{{escaped}}}\n```"
        return f"{prefix}{title}\n\n{mark}"

    marked = re.sub(r"(?m)^(?P<prefix>#{1,6}\s+)(?P<title>[^\n]+)$", replace, body)
    return marked, {"enabled": True, "source": normalized_source, "marks_inserted": count}


def delivery_page_margins(delivery: dict[str, Any]) -> list[str]:
    if delivery.get("mode") != "bound":
        return []
    margins = delivery.get("margins", {}) if isinstance(delivery.get("margins"), dict) else {}
    return [f"{key}={margins[key]}" for key in ("inner", "outer", "top", "bottom") if margins.get(key)]


def delivery_boundary(delivery: dict[str, Any]) -> dict[str, Any]:
    mode = delivery.get("mode", "screen") if isinstance(delivery, dict) else "screen"
    if mode != "bound":
        return {"delivery_mode": mode}
    colophon = delivery.get("colophon", {}) if isinstance(delivery.get("colophon"), dict) else {}
    return {
        "delivery_mode": "bound",
        "delivery_binding": delivery.get("binding"),
        "delivery_duplex": delivery.get("duplex"),
        "delivery_page_numbers": delivery.get("page_numbers"),
        "delivery_margins": deepcopy(delivery.get("margins", {})),
        "delivery_running_headers": deepcopy(delivery.get("running_headers", {})),
        "delivery_footer_metadata": deepcopy(delivery.get("footer_metadata", {})),
        "delivery_colophon_enabled": bool(colophon.get("enabled")),
        "delivery_colophon_placement": colophon.get("placement", ""),
        "delivery_illumination": deepcopy(delivery.get("illumination", {})),
        "delivery_signature": deepcopy(delivery.get("signature", {})),
    }


def bound_colophon_block(*, title: str, author: str, date: str, render_id: str, delivery: dict[str, Any]) -> str:
    """Return raw LaTeX for a simple title-verso colophon page."""

    lines = [
        "```{=latex}",
        "\\thispagestyle{empty}",
        "\\providecommand{\\OFBoundColophon}{}",
        "\\OFBoundColophon",
        "\\begingroup",
        "\\vspace*{\\fill}",
        "\\begin{center}",
        "{\\small\\scshape Production Colophon\\par}",
        "\\vspace{0.8em}",
        _latex_line(title, "Title"),
        _latex_line(author, "Steward"),
        _latex_line(date, "Edition date"),
        _latex_line(render_id, "Render"),
        _latex_line(str(delivery.get("binding", "")), "Binding"),
        "\\end{center}",
        "\\vspace*{\\fill}",
        "\\endgroup",
        "\\clearpage",
        "```",
    ]
    return "\n".join(line for line in lines if line)


def insert_title_verso_colophon(body: str, colophon_block: str) -> tuple[str, bool]:
    """Insert colophon after the first title-page clearpage when available."""

    if not colophon_block.strip():
        return body, False
    marker = "\\clearpage"
    index = body.find(marker)
    if index == -1:
        return f"{colophon_block}\n\n{body}", True
    insertion = _raw_latex_fence_end_after(body, index + len(marker))
    if insertion is None:
        insertion = index + len(marker)
    return f"{body[:insertion].rstrip()}\n\n{colophon_block}\n\n{body[insertion:].lstrip()}", True


def _raw_latex_fence_end_after(body: str, position: int) -> int | None:
    """Return enclosing raw-LaTeX fence end if position is inside one."""

    fence_start = body.rfind("```{=latex}", 0, position)
    if fence_start == -1:
        return None
    fence_end_before = body.rfind("\n```", 0, position)
    if fence_end_before > fence_start:
        return None
    fence_end_after = body.find("\n```", position)
    if fence_end_after == -1:
        return None
    return fence_end_after + len("\n```")


def _normalize_token(value: Any, *, default: str) -> str:
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        raise ValueError("delivery tokens must be strings")
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_delivery_margins(value: Any, *, scope: str) -> dict[str, str]:
    if value in (None, ""):
        value = {}
    if not isinstance(value, dict):
        raise ValueError(f"{scope} must be a mapping")
    unknown = sorted(str(key) for key in value if key not in BOUND_DEFAULT_MARGINS)
    if unknown:
        raise ValueError(f"{scope} supports only: {', '.join(BOUND_DEFAULT_MARGINS)}")
    margins = dict(BOUND_DEFAULT_MARGINS)
    for key, raw in value.items():
        if raw not in (None, ""):
            margins[str(key)] = _normalize_margin_dimension(raw, scope=f"{scope}.{key}")
    return margins


def _normalize_colophon(value: Any, *, scope: str) -> dict[str, Any]:
    if value in (None, ""):
        value = {}
    if value is False:
        return {"enabled": False, "placement": "title_verso"}
    if value is True:
        value = {"enabled": True}
    if not isinstance(value, dict):
        raise ValueError(f"{scope} must be a mapping")
    enabled = bool(value.get("enabled", True))
    placement = _normalize_token(value.get("placement", "title_verso"), default="title_verso")
    if placement not in SUPPORTED_COLOPHON_PLACEMENTS:
        raise ValueError(f"{scope}.placement must be one of: {', '.join(sorted(SUPPORTED_COLOPHON_PLACEMENTS))}")
    return {"enabled": enabled, "placement": placement}


def _normalize_running_headers(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "enabled": bool(value.get("enabled", False)),
        "source": _normalize_token(value.get("source", "chapter"), default="chapter"),
        "suppress_on": list(value.get("suppress_on", ["title_page", "title_verso", "blank_pages", "chapter_openers"])),
    }


def _normalize_illumination(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    return {
        "enabled": bool(value.get("enabled", False)),
        "rail": _normalize_token(value.get("rail", "outer"), default="outer"),
        "width": str(value.get("width", "0.45in")),
        "reserve_space": bool(value.get("reserve_space", False)),
        "placement": _normalize_token(value.get("placement", "chapter_openers"), default="chapter_openers"),
        "assets": list(value.get("assets", [])) if isinstance(value.get("assets", []), list) else [],
    }


def _latex_escape(value: str) -> str:
    return str(value).replace("\\", r"\\").replace("&", r"\&").replace("%", r"\%").replace("#", r"\#").replace("_", r"\_")


def _latex_line(value: str, label: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    return f"{{\\scriptsize {label}: {_latex_escape(value)}\\par}}"
