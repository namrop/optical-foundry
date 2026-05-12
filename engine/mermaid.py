"""Mermaid chart preprocessing for Optical Foundry Markdown/Pandoc renders.

The renderer path accepts canonical Markdown. Mermaid is not a native Pandoc PDF
feature, so Foundry treats Mermaid fences as a pre-Pandoc asset compilation pass:

1. discover fenced ```mermaid blocks;
2. render each block to a deterministic generated figure path;
3. rewrite the fence to a normal Markdown image reference;
4. return figure/evidence metadata for the final render sidecar.

Theme resolution is local-first and profile-derived. It reads the same profile
defaults/style surfaces used by the Pandoc renderer, extracts LaTeX palette
colors where available, and exposes both Mermaid `themeVariables` and a
Vega-shaped palette object for future Vega/Vega-Lite chart renderers.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from engine.manifest_compiler import _split_frontmatter_and_body
from engine.profile_resolver import ResolvedProfile, resolve_profile

RendererFn = Callable[[str, Path, dict[str, Any]], None]

PINNED_MERMAID_CLI_PACKAGE = "@mermaid-js/mermaid-cli@11.14.0"

TRUE_FALLBACK_PALETTE = {
    "primary": "#0B1220",
    "accent": "#C6A35E",
    "secondary": "#2A2F3A",
    "background": "#F6F5F2",
    "surface": "#FFFFFF",
    "text": "#0B1220",
    "muted": "#6B7280",
}

CSS_NAMED_COLORS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "gray": "#808080",
    "grey": "#808080",
    "red": "#FF0000",
    "green": "#008000",
    "blue": "#0000FF",
}


@dataclass(frozen=True)
class MermaidPreprocessResult:
    """Result of rewriting one Markdown source for Mermaid assets."""

    rewritten_source: Path
    figure_inventory: list[dict[str, Any]]
    theme: dict[str, Any]
    changed: bool


@dataclass(frozen=True)
class MermaidRenderError(Exception):
    """Raised when Mermaid CLI rendering fails."""

    message: str

    def __str__(self) -> str:
        return self.message


def resolve_profile_chart_theme(profile_id: str, frontmatter: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve a profile-derived chart theme.

    Explicit source/frontmatter chart settings win. Otherwise, use profile
    defaults/style package colors. If those are absent, use the true fallback
    palette so Mermaid rendering is deterministic.
    """

    resolved = resolve_profile(profile_id)
    variables = _merged_defaults_variables(resolved.defaults_stack)
    style_colors, style_hypersetup, style_shade = _profile_style_colors(resolved, variables)

    palette = dict(TRUE_FALLBACK_PALETTE)
    source = "fallback"

    def color_from_name_or_hex(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        direct = _normalize_hex(text)
        if direct:
            return direct
        return style_colors.get(text) or CSS_NAMED_COLORS.get(text.lower())

    primary = (
        color_from_name_or_hex(style_hypersetup.get("linkcolor"))
        or color_from_name_or_hex(variables.get("linkcolor"))
        or _pick_named_color(style_colors, ["Primary", "Navy", "Ink"])
    )
    accent = (
        color_from_name_or_hex(style_hypersetup.get("urlcolor"))
        or color_from_name_or_hex(variables.get("urlcolor"))
        or _pick_named_color(style_colors, ["Accent", "Gold", "Link"])
    )
    secondary = _pick_named_color(style_colors, ["Slate", "Muted", "Secondary", "Dark"])
    background = color_from_name_or_hex(style_shade) or _pick_named_color(style_colors, ["Light", "Shade", "OffWhite"])
    surface = _pick_named_color(style_colors, ["OffWhite", "Light", "Shade"])

    for key, value in {
        "primary": primary,
        "accent": accent,
        "secondary": secondary,
        "background": background,
        "surface": surface,
    }.items():
        if value:
            palette[key] = value
            source = "profile"

    fm_palette = _frontmatter_chart_palette(frontmatter or {})
    if fm_palette:
        palette.update(fm_palette)
        source = "frontmatter"

    palette_values = _dedupe_palette(
        [palette["primary"], palette["accent"], palette["secondary"], palette["muted"], palette["background"]]
    )
    return {
        "source": source,
        "profile_id": profile_id,
        "canonical_profile_id": resolved.canonical_profile_id,
        "palette": palette_values,
        "tokens": palette,
        "theme": "base",
        "themeVariables": _mermaid_theme_variables(palette, palette_values),
        "vega": {
            "range": {
                "category": palette_values,
                "ordinal": palette_values,
                "ramp": palette_values,
            },
            "background": palette["surface"],
            "config": {
                "axis": {"labelColor": palette["secondary"], "titleColor": palette["text"]},
                "legend": {"labelColor": palette["secondary"], "titleColor": palette["text"]},
                "title": {"color": palette["text"]},
            },
        },
    }


def preprocess_mermaid_blocks(
    markdown_path: Path,
    profile_id: str,
    output_dir: Path,
    render_id: str,
    renderer: RendererFn | None = None,
    output_format: str = "pdf",
) -> MermaidPreprocessResult:
    """Render Mermaid fences and rewrite them to Markdown image references.

    `renderer` is injectable for tests. The default renderer shells out to
    `mmdc` / Mermaid CLI and writes the requested output file.
    """

    markdown_path = Path(markdown_path)
    original_markdown_path = markdown_path
    output_dir = Path(output_dir).resolve()
    text = markdown_path.read_text()
    frontmatter, _body = _split_frontmatter_and_body(text)
    theme = resolve_profile_chart_theme(profile_id, frontmatter or {})

    matches = list(_MERMAID_FENCE_RE.finditer(text))
    if not matches:
        return MermaidPreprocessResult(markdown_path, [], theme, False)

    asset_dir = output_dir / "figures" / "mermaid"
    asset_dir.mkdir(parents=True, exist_ok=True)
    rewritten_dir = output_dir / "_preprocessed"
    rewritten_dir.mkdir(parents=True, exist_ok=True)

    actual_renderer = renderer or render_mermaid_cli
    figure_inventory: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        index = len(figure_inventory) + 1
        mermaid_source = match.group("body").strip() + "\n"
        digest = hashlib.sha256(mermaid_source.encode("utf-8")).hexdigest()[:16]
        suffix = output_format.lstrip(".")
        figure_path = asset_dir / f"{render_id}-mermaid-{index:02d}-{digest}.{suffix}"
        config = mermaid_cli_config(theme)
        actual_renderer(mermaid_source, figure_path, config)
        figure_inventory.append(
            {
                "kind": "mermaid",
                "index": index,
                "path": str(figure_path),
                "source_path": str(original_markdown_path),
                "digest_sha256": hashlib.sha256(mermaid_source.encode("utf-8")).hexdigest(),
                "output_format": suffix,
                "theme": theme,
            }
        )
        return f"![Mermaid chart {index}]({figure_path}){{#fig:mermaid-{index}}}"

    rewritten_text = _MERMAID_FENCE_RE.sub(replace, text)
    rewritten_source = rewritten_dir / f"{render_id}.mermaid.md"
    rewritten_source.write_text(rewritten_text)
    return MermaidPreprocessResult(rewritten_source, figure_inventory, theme, True)


def mermaid_cli_config(theme: dict[str, Any]) -> dict[str, Any]:
    """Return Mermaid CLI config from a resolved chart theme."""

    return {
        "securityLevel": "strict",
        "theme": theme.get("theme", "base"),
        "themeVariables": theme.get("themeVariables", {}),
    }


def resolve_mermaid_command() -> list[str]:
    """Resolve the local Mermaid CLI command.

    Preference order:
    1. `MERMAID_CLI` explicit executable path;
    2. `mmdc` already on PATH;
    3. pinned `npx -y @mermaid-js/mermaid-cli@11.14.0` fallback.

    The fallback still renders locally; it only uses npm to materialize the
    pinned CLI package when it is not otherwise installed.
    """

    explicit = os.environ.get("MERMAID_CLI", "").strip()
    if explicit:
        return [explicit]
    mmdc = shutil.which("mmdc")
    if mmdc:
        return [mmdc]
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", PINNED_MERMAID_CLI_PACKAGE]
    raise MermaidRenderError(
        "Mermaid CLI unavailable: set MERMAID_CLI, install `mmdc`, or install npm/npx for the pinned Mermaid CLI fallback."
    )


def render_mermaid_cli(source: str, output_path: Path, config: dict[str, Any]) -> None:
    """Render one Mermaid source string through Mermaid CLI (`mmdc`)."""

    command_prefix = resolve_mermaid_command()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="of_mermaid_") as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "chart.mmd"
        config_path = tmp_path / "config.json"
        input_path.write_text(source)
        config_path.write_text(json.dumps(config, indent=2))
        cmd = [*command_prefix, "-i", str(input_path), "-o", str(output_path), "-c", str(config_path), "--quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not output_path.exists():
            raise MermaidRenderError(f"Mermaid CLI failed ({result.returncode}): {result.stderr[-1000:]}")


_MERMAID_FENCE_RE = re.compile(
    r"^```mermaid[^\n]*\n(?P<body>.*?)^```\s*$",
    flags=re.MULTILINE | re.DOTALL,
)


def _merged_defaults_variables(defaults_stack: list[Path]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for defaults_path in defaults_stack:
        try:
            import yaml

            data = yaml.safe_load(defaults_path.read_text()) or {}
        except Exception:
            data = {}
        if isinstance(data, dict) and isinstance(data.get("variables"), dict):
            variables.update(data["variables"])
    return variables


def _profile_style_colors(
    resolved: ResolvedProfile, variables: dict[str, Any]
) -> tuple[dict[str, str], dict[str, str], str | None]:
    style_paths = _candidate_style_paths(resolved, variables)
    colors: dict[str, str] = {}
    hypersetup: dict[str, str] = {}
    shade: str | None = None
    for path in style_paths:
        if not path.exists():
            continue
        text = path.read_text(errors="replace")
        colors.update(_parse_latex_colors(text))
        hypersetup.update(_parse_hypersetup_colors(text))
        shade_match = list(re.finditer(r"\\definecolor\{shadecolor\}\{HTML\}\{([0-9A-Fa-f]{6})\}", text))
        if shade_match:
            shade = f"#{shade_match[-1].group(1).upper()}"
    return colors, hypersetup, shade


def _candidate_style_paths(resolved: ResolvedProfile, variables: dict[str, Any]) -> list[Path]:
    texmf = resolved.render_environment.texmfhome
    if texmf is None:
        return []
    roots = [texmf / "tex" / "latex" / "yugen", texmf / "tex" / "latex" / "generic", texmf / "tex" / "latex" / "resume"]
    packages: list[str] = []
    for key in ("genericstyle", "yugenstyle", "elianstyle"):
        value = variables.get(key)
        if isinstance(value, str) and value:
            packages.append(value)
    if any(pkg.startswith("yugen") for pkg in packages):
        packages.insert(0, "yugencommon")
    paths: list[Path] = []
    for package in packages:
        for root in roots:
            candidate = root / f"{package}.sty"
            if candidate.exists() and candidate not in paths:
                paths.append(candidate)
    return paths


def _parse_latex_colors(text: str) -> dict[str, str]:
    colors: dict[str, str] = {}
    for match in re.finditer(r"\\definecolor\{([^}]+)\}\{HTML\}\{([0-9A-Fa-f]{6})\}", text):
        colors[match.group(1)] = f"#{match.group(2).upper()}"
    return colors


def _parse_hypersetup_colors(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in ("linkcolor", "urlcolor", "citecolor"):
        matches = list(re.finditer(rf"{key}\s*=\s*([A-Za-z][A-Za-z0-9]*)", text))
        if matches:
            result[key] = matches[-1].group(1)
    return result


def _normalize_hex(value: str) -> str | None:
    value = value.strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value.upper()
    if re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        return f"#{value.upper()}"
    return None


def _pick_named_color(colors: dict[str, str], priority_fragments: list[str]) -> str | None:
    for fragment in priority_fragments:
        for name, hex_value in colors.items():
            if fragment.lower() in name.lower():
                return hex_value
    return None


def _frontmatter_chart_palette(frontmatter: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    candidates: dict[str, Any] = {}
    if isinstance(frontmatter.get("chart_theme"), dict):
        candidates.update(frontmatter["chart_theme"])
    if isinstance(frontmatter.get("variables"), dict):
        candidates.update(frontmatter["variables"])
    key_map = {
        "chart_primary": "primary",
        "chart_accent": "accent",
        "chart_secondary": "secondary",
        "chart_background": "background",
        "chart_surface": "surface",
        "chart_text": "text",
        "chart_muted": "muted",
        "primary": "primary",
        "accent": "accent",
        "secondary": "secondary",
        "background": "background",
        "surface": "surface",
        "text": "text",
        "muted": "muted",
    }
    for key, value in candidates.items():
        mapped = key_map.get(str(key))
        normalized = _normalize_hex(str(value)) if mapped and isinstance(value, str) else None
        if mapped and normalized:
            out[mapped] = normalized
    return out


def _dedupe_palette(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _mermaid_theme_variables(palette: dict[str, str], palette_values: list[str]) -> dict[str, Any]:
    return {
        "primaryColor": palette["primary"],
        "primaryTextColor": palette["surface"],
        "primaryBorderColor": palette["accent"],
        "lineColor": palette["primary"],
        "secondaryColor": palette["accent"],
        "tertiaryColor": palette["background"],
        "background": palette["surface"],
        "mainBkg": palette["surface"],
        "textColor": palette["text"],
        "pie1": palette_values[0],
        "pie2": palette_values[1] if len(palette_values) > 1 else palette_values[0],
        "pie3": palette_values[2] if len(palette_values) > 2 else palette_values[0],
        "pie4": palette_values[3] if len(palette_values) > 3 else palette_values[0],
        "xyChart": {
            "backgroundColor": palette["surface"],
            "titleColor": palette["text"],
            "xAxisLabelColor": palette["secondary"],
            "yAxisLabelColor": palette["secondary"],
            "plotColorPalette": ", ".join(palette_values),
        },
    }
