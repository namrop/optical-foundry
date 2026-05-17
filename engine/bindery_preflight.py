"""Print/bindery preflight evidence for bound Optical Foundry PDFs.

This module is intentionally advisory: it records facts a printer/bindery will
ask for, and distinguishes prototype-ready files from vendor-independent
press-ready files without silently changing the rendered PDF.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re
import shutil
import subprocess

from engine.page_size import normalize_page_size
from engine.projection_plan import ProjectionPlan

POINTS_PER_INCH = 72.0
PAGE_SIZE_INCHES = {
    "letter": (8.5, 11.0),
    "half_letter": (5.5, 8.5),
    "a4": (8.27, 11.69),
    "a5": (5.83, 8.27),
}


def generate_bindery_preflight(
    pdf_path: str | Path,
    *,
    out_dir: str | Path,
    plan: ProjectionPlan,
    imposition: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Inspect a successful bound render and write bindery preflight sidecars."""

    if plan.delivery.get("mode") != "bound":
        return None
    pdf = Path(pdf_path).expanduser().resolve()
    dest = Path(out_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    pdfinfo_text = _run_tool(["pdfinfo", "-box", str(pdf)])
    pdffonts_text = _run_tool(["pdffonts", str(pdf)])
    pdfimages_text = _run_tool(["pdfimages", "-list", str(pdf)])
    safe_area_guide = write_safe_area_guide_tex(plan, dest)

    report = build_bindery_preflight_report(
        pdf_path=pdf,
        pdfinfo_text=pdfinfo_text,
        pdffonts_text=pdffonts_text,
        pdfimages_text=pdfimages_text,
        page_size=plan.page_size,
        page_margins=plan.page_margins,
        delivery=plan.delivery,
        imposition=imposition,
        safe_area_guide=safe_area_guide,
    )
    report_path = dest / f"{plan.render_id}.bindery_preflight.json"
    report["report_json"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_bindery_preflight_report(
    *,
    pdf_path: str | Path,
    pdfinfo_text: str,
    pdffonts_text: str,
    pdfimages_text: str,
    page_size: str,
    page_margins: list[str],
    delivery: dict[str, Any],
    imposition: dict[str, Any] | None,
    safe_area_guide: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build an advisory print/bindery report from preflight command output."""

    boxes = parse_pdfinfo_boxes(pdfinfo_text)
    fonts = parse_pdffonts(pdffonts_text)
    images = parse_pdfimages(pdfimages_text)
    page = normalize_page_size(page_size)
    expected_width, expected_height = PAGE_SIZE_INCHES[page]
    trim = boxes.get("TrimBox") or boxes.get("CropBox") or boxes.get("MediaBox") or {}
    trim_inches = _box_inches(trim) if trim else {"width": expected_width, "height": expected_height}
    bleed = boxes.get("BleedBox") or trim
    bleed_inches = _box_inches(bleed) if bleed else trim_inches
    has_bleed = bool(bleed_inches["width"] > trim_inches["width"] or bleed_inches["height"] > trim_inches["height"])

    blocking: list[str] = []
    if not fonts["all_embedded"]:
        blocking.append("fonts_not_embedded")
    if not has_bleed:
        blocking.append("no_bleed")
    if images["rgb_images"] > 0:
        blocking.append("rgb_images_present")
    if images["below_300ppi"] > 0:
        blocking.append("images_below_300ppi")

    single_pages = _is_single_page_pdf(trim_inches, expected_width, expected_height)
    prototype_ready = single_pages and fonts["all_embedded"] and not bool(_tool_error(pdfinfo_text))
    press_ready = prototype_ready and not blocking
    imposition_status = imposition.get("status") if isinstance(imposition, dict) else "not_requested"

    return {
        "schema_version": "bindery_preflight_v1",
        "pdf_path": str(Path(pdf_path)),
        "summary": {
            "page_size": page,
            "trim_size_inches": trim_inches,
            "single_pages": single_pages,
            "binding": delivery.get("binding", "unknown"),
            "imposition_status": imposition_status,
        },
        "recommendation": {
            "send_default": "single_page_pdf",
            "send_imposed_only_if_requested": True,
            "notes": [
                "Most printers/binderies want final-trim single pages, not customer-imposed spreads.",
                "Use imposed PDF as local/prototype booklet lane or if the vendor explicitly requests imposed signatures.",
            ],
        },
        "page_boxes": {
            "raw": boxes,
            "trim_inches": trim_inches,
            "bleed_inches": bleed_inches,
            "has_bleed": has_bleed,
            "expected_trim_inches": {"width": expected_width, "height": expected_height},
        },
        "fonts": fonts,
        "images": images,
        "layout": {
            "page_margins": page_margins,
            "delivery": delivery,
            "safe_area_guide": safe_area_guide or {},
        },
        "safe_area_guide": safe_area_guide or {},
        "readiness": {
            "prototype_ready": prototype_ready,
            "vendor_independent_press_ready": press_ready,
            "blocking_press_ready_issues": blocking,
            "vendor_questions": [
                "Do you want single pages or imposed signatures?",
                "Do you require 0.125in bleed?",
                "Do you require CMYK or accept RGB?",
                "Do you require PDF/X-1a or PDF/X-4?",
                "Do you want crop marks/printer marks or clean pages?",
                "For deckled edges, what trim variance should the art tolerate?",
            ],
        },
        "tool_errors": [err for err in [_tool_error(pdfinfo_text), _tool_error(pdffonts_text), _tool_error(pdfimages_text)] if err],
    }


def write_safe_area_guide_tex(
    plan: ProjectionPlan,
    out_dir: str | Path,
    *,
    deckle_zone: str = "0.20in",
    critical_safe_inset: str = "0.25in",
) -> dict[str, Any]:
    """Write a bound-layout guide TeX/PDF sidecar showing trim, body, rail, deckle."""

    dest = Path(out_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    page_w, page_h = PAGE_SIZE_INCHES[normalize_page_size(plan.page_size)]
    margins = _margin_map(plan.page_margins)
    inner = margins.get("inner", margins.get("left", margins.get("margin", 1.0)))
    outer = margins.get("outer", margins.get("right", margins.get("margin", 1.0)))
    top = margins.get("top", margins.get("margin", 1.0))
    bottom = margins.get("bottom", margins.get("margin", 1.0))
    text_w = round(page_w - inner - outer, 3)
    text_h = round(page_h - top - bottom, 3)
    illumination = plan.delivery.get("illumination", {}) if isinstance(plan.delivery.get("illumination", {}), dict) else {}
    rail_w = _dimension_to_inches(illumination.get("width", "0.45in")) if illumination.get("enabled") else 0.0
    sep = 0.05 if rail_w else 0.0
    deckle = _dimension_to_inches(deckle_zone)
    critical = _dimension_to_inches(critical_safe_inset)

    recto_body = {"x": round(inner, 3), "y": round(top, 3), "width": text_w, "height": text_h}
    verso_body = {"x": round(outer, 3), "y": round(top, 3), "width": text_w, "height": text_h}
    recto_rail = _rail_box(page_w, outer, top, text_h, rail_w, sep, recto=True)
    verso_rail = _rail_box(page_w, outer, top, text_h, rail_w, sep, recto=False)
    tex_path = dest / f"{plan.render_id}.safe_area_guide.tex"
    pdf_path = tex_path.with_suffix(".pdf")
    tex_path.write_text(
        _safe_area_guide_tex(
            page_w=page_w,
            page_h=page_h,
            recto_body=recto_body,
            verso_body=verso_body,
            recto_rail=recto_rail,
            verso_rail=verso_rail,
            deckle=deckle,
            critical=critical,
        ),
        encoding="utf-8",
    )
    status = "tex_written"
    error = ""
    xelatex = shutil.which("xelatex") or ("/Library/TeX/texbin/xelatex" if Path("/Library/TeX/texbin/xelatex").exists() else "")
    if xelatex:
        proc = subprocess.run(
            [xelatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=dest,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if proc.returncode == 0 and pdf_path.exists():
            status = "pdf_written"
        else:
            status = "tex_written_pdf_failed"
            error = (proc.stderr or proc.stdout)[-800:]

    result = {
        "status": status,
        "tex_path": str(tex_path),
        "pdf_path": str(pdf_path) if pdf_path.exists() else "",
        "trim_inches": {"width": page_w, "height": page_h},
        "deckle_zone_inches": round(deckle, 3),
        "critical_safe_inset_inches": round(critical, 3),
        "body_box_inches": {"recto": recto_body, "verso": verso_body},
        "rail_box_inches": {"recto": recto_rail, "verso": verso_rail},
    }
    if error:
        result["error"] = error
    return result


def parse_pdfinfo_boxes(text: str) -> dict[str, Any]:
    boxes: dict[str, Any] = {}
    pages = re.search(r"^Pages:\s+(\d+)", text, re.MULTILINE)
    if pages:
        boxes["Pages"] = int(pages.group(1))
    encrypted = re.search(r"^Encrypted:\s+(\S+)", text, re.MULTILINE)
    if encrypted:
        boxes["Encrypted"] = encrypted.group(1)
    version = re.search(r"^PDF version:\s+(\S+)", text, re.MULTILINE)
    if version:
        boxes["PDFVersion"] = version.group(1)
    for name in ("MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox"):
        match = re.search(rf"^{name}:\s+([-0-9.]+)\s+([-0-9.]+)\s+([-0-9.]+)\s+([-0-9.]+)", text, re.MULTILINE)
        if match:
            x0, y0, x1, y1 = (float(match.group(i)) for i in range(1, 5))
            boxes[name] = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "width_pt": x1 - x0, "height_pt": y1 - y0}
    return boxes


def parse_pdffonts(text: str) -> dict[str, Any]:
    fonts: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("name") or not stripped.replace(" ", "").replace("-", ""):
            continue
        parts = stripped.split()
        if len(parts) < 7:
            continue
        emb = parts[-5].lower()
        sub = parts[-4].lower()
        uni = parts[-3].lower()
        fonts.append({"name": parts[0], "embedded": emb == "yes", "subset": sub == "yes", "unicode": uni == "yes"})
    return {
        "count": len(fonts),
        "all_embedded": all(font["embedded"] for font in fonts) if fonts else False,
        "fonts": fonts,
    }


def parse_pdfimages(text: str) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("page") or not stripped.replace(" ", "").replace("-", ""):
            continue
        parts = stripped.split()
        if len(parts) < 14 or not parts[0].isdigit():
            continue
        image_type = parts[2].lower()
        if image_type == "smask":
            continue
        try:
            x_ppi = int(float(parts[12]))
            y_ppi = int(float(parts[13]))
        except Exception:
            continue
        color = parts[5].lower()
        images.append({"page": int(parts[0]), "type": image_type, "color": color, "x_ppi": x_ppi, "y_ppi": y_ppi})
    min_ppi = min((min(img["x_ppi"], img["y_ppi"]) for img in images), default=None)
    return {
        "count": len(images),
        "min_effective_ppi": min_ppi,
        "below_300ppi": sum(1 for img in images if min(img["x_ppi"], img["y_ppi"]) < 300),
        "rgb_images": sum(1 for img in images if img["color"] == "rgb"),
        "colors": sorted({img["color"] for img in images}),
        "images": images[:50],
    }


def _safe_area_guide_tex(
    *,
    page_w: float,
    page_h: float,
    recto_body: dict[str, float],
    verso_body: dict[str, float],
    recto_rail: dict[str, float],
    verso_rail: dict[str, float],
    deckle: float,
    critical: float,
) -> str:
    # picture y=0 is bottom; input boxes are top-origin inches.
    def put_box(box: dict[str, float], color: str, label: str = "") -> str:
        x = box["x"]
        y = page_h - box["y"] - box["height"]
        text = rf"\scriptsize {label}" if label else ""
        return rf"\textcolor{{{color}}}{{\put({x:.3f},{y:.3f}){{\framebox({box['width']:.3f},{box['height']:.3f}){{{text}}}}}}}"

    def fill_box(box: dict[str, float], color: str) -> str:
        x = box["x"]
        y = page_h - box["y"] - box["height"]
        return rf"\put({x:.3f},{y:.3f}){{\textcolor{{{color}}}{{\rule{{{box['width']:.3f}in}}{{{box['height']:.3f}in}}}}}}"

    legend = rf"""\put(0.12,{page_h - 0.45:.3f}){{\scriptsize \textcolor{{LightGoldenrod3}}{{\rule{{0.16in}}{{0.05in}}}} Deckle / sacrificial zone}}
\put(0.12,{page_h - 0.62:.3f}){{\scriptsize \textcolor{{IndianRed3}}{{\rule{{0.16in}}{{0.05in}}}} Critical-safe inset}}
\put(0.12,{page_h - 0.79:.3f}){{\scriptsize \textcolor{{RoyalBlue3}}{{\rule{{0.16in}}{{0.05in}}}} Body text block}}
\put(0.12,{page_h - 0.96:.3f}){{\scriptsize \textcolor{{DarkOliveGreen4}}{{\rule{{0.16in}}{{0.05in}}}} Outer illumination rail}}"""

    recto_deckle = {"x": page_w - deckle, "y": 0.0, "width": deckle, "height": page_h}
    verso_deckle = {"x": 0.0, "y": 0.0, "width": deckle, "height": page_h}
    recto_critical = {"x": page_w - critical, "y": 0.0, "width": critical, "height": page_h}
    verso_critical = {"x": 0.0, "y": 0.0, "width": critical, "height": page_h}
    return rf"""
\documentclass{{article}}
\usepackage[paperwidth={page_w}in,paperheight={page_h}in,margin=0in]{{geometry}}
\usepackage[x11names]{{xcolor}}
\pagestyle{{empty}}
\setlength{{\unitlength}}{{1in}}
\begin{{document}}
\noindent\begin{{picture}}({page_w},{page_h})
\put(0.12,{page_h - 0.25:.3f}){{\scriptsize Recto/right-hand page safe-area guide}}
{fill_box(recto_body, "RoyalBlue3!6")}
{fill_box(recto_critical, "IndianRed3!14")}
{fill_box(recto_rail, "DarkOliveGreen4!16") if recto_rail['width'] else ''}
{fill_box(recto_deckle, "LightGoldenrod3!28")}
{put_box(recto_deckle, "LightGoldenrod3")}
{put_box(recto_critical, "IndianRed3")}
{put_box(recto_body, "RoyalBlue3", "Body")}
{put_box(recto_rail, "DarkOliveGreen4") if recto_rail['width'] else ''}
{legend}
\end{{picture}}
\newpage
\noindent\begin{{picture}}({page_w},{page_h})
\put(0.12,{page_h - 0.25:.3f}){{\scriptsize Verso/left-hand page safe-area guide}}
{fill_box(verso_body, "RoyalBlue3!6")}
{fill_box(verso_critical, "IndianRed3!14")}
{fill_box(verso_rail, "DarkOliveGreen4!16") if verso_rail['width'] else ''}
{fill_box(verso_deckle, "LightGoldenrod3!28")}
{put_box(verso_deckle, "LightGoldenrod3")}
{put_box(verso_critical, "IndianRed3")}
{put_box(verso_body, "RoyalBlue3", "Body")}
{put_box(verso_rail, "DarkOliveGreen4") if verso_rail['width'] else ''}
{legend}
\end{{picture}}
\end{{document}}
""".lstrip()


def _rail_box(page_w: float, outer: float, top: float, text_h: float, rail_w: float, sep: float, *, recto: bool) -> dict[str, float]:
    if rail_w <= 0:
        return {"x": 0.0, "y": top, "width": 0.0, "height": text_h}
    x = page_w - outer + sep if recto else outer - sep - rail_w
    return {"x": round(max(0.0, x), 3), "y": round(top, 3), "width": round(rail_w, 3), "height": round(text_h, 3)}


def _margin_map(options: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in options:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        result[key.strip()] = _dimension_to_inches(value.strip())
    if "margin" in result:
        for key in ("inner", "outer", "top", "bottom", "left", "right"):
            result.setdefault(key, result["margin"])
    return result


def _dimension_to_inches(value: Any) -> float:
    text = str(value).strip()
    match = re.match(r"^(\d+(?:\.\d+)?|\.\d+)(in|pt|mm|cm)$", text)
    if not match:
        raise ValueError(f"unsupported TeX dimension for bindery preflight: {value}")
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "in":
        return number
    if unit == "pt":
        return number / POINTS_PER_INCH
    if unit == "mm":
        return number / 25.4
    if unit == "cm":
        return number / 2.54
    raise ValueError(value)


def _box_inches(box: dict[str, Any]) -> dict[str, float]:
    return {"width": round(float(box["width_pt"]) / POINTS_PER_INCH, 3), "height": round(float(box["height_pt"]) / POINTS_PER_INCH, 3)}


def _is_single_page_pdf(trim_inches: dict[str, float], expected_width: float, expected_height: float) -> bool:
    return abs(trim_inches["width"] - expected_width) < 0.02 and abs(trim_inches["height"] - expected_height) < 0.02


def _tool_error(text: str) -> str:
    return text[8:] if text.startswith("__ERROR__") else ""


def _run_tool(command: list[str]) -> str:
    if not shutil.which(command[0]):
        return f"__ERROR__{command[0]} unavailable"
    proc = subprocess.run(command, text=True, capture_output=True, timeout=90)
    if proc.returncode != 0:
        return f"__ERROR__{command[0]} failed: {(proc.stderr or proc.stdout).strip()}"
    return proc.stdout
