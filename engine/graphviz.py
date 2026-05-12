"""Graphviz/DOT topology diagram preprocessing for Optical Foundry renders.

Graphviz/DOT is treated as a local generated-asset lane: fenced ```dot or
```graphviz diagrams are validated, lightly themed with bounded default graph /
node / edge attributes, rendered through local native `dot`, rewritten to ordinary
Markdown image references, and recorded in render evidence. DOT source is render
data, not agent instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from engine.manifest_compiler import _split_frontmatter_and_body
from engine.mermaid import resolve_profile_chart_theme

PINNED_GRAPHVIZ_VERSION = "14.1.5"
GRAPHVIZ_RENDERER_NAME = "graphviz_dot"
LOCAL_DOT_BINARY = Path(__file__).resolve().parents[1] / ".tools" / "graphviz" / f"v{PINNED_GRAPHVIZ_VERSION}" / "dot"
MAX_DOT_SOURCE_BYTES = 500_000

GraphvizRendererFn = Callable[[str, Path, dict[str, Any]], None]


@dataclass(frozen=True)
class GraphvizPreprocessResult:
    """Result of rewriting one Markdown source for Graphviz/DOT generated figures."""

    rewritten_source: Path
    figure_inventory: list[dict[str, Any]]
    theme: dict[str, Any]
    changed: bool


@dataclass(frozen=True)
class GraphvizRenderError(Exception):
    """Raised when Graphviz/DOT validation or rendering fails."""

    message: str

    def __str__(self) -> str:
        return self.message


def preprocess_graphviz_blocks(
    markdown_path: Path,
    profile_id: str,
    output_dir: Path,
    render_id: str,
    renderer: GraphvizRendererFn | None = None,
    output_format: str = "svg",
) -> GraphvizPreprocessResult:
    """Render DOT/Graphviz fences and rewrite them to Markdown image references."""

    markdown_path = Path(markdown_path)
    original_markdown_path = markdown_path
    output_dir = Path(output_dir).resolve()
    text = markdown_path.read_text()
    frontmatter, _body = _split_frontmatter_and_body(text)
    theme = resolve_profile_chart_theme(profile_id, frontmatter or {})

    matches = list(_GRAPHVIZ_FENCE_RE.finditer(text))
    if not matches:
        return GraphvizPreprocessResult(markdown_path, [], theme, False)

    asset_dir = output_dir / "figures" / "graphviz"
    source_dir = asset_dir / "sources"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    rewritten_dir = output_dir / "_preprocessed"
    rewritten_dir.mkdir(parents=True, exist_ok=True)

    actual_renderer = renderer or render_graphviz_cli
    figure_inventory: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        index = len(figure_inventory) + 1
        raw_source = match.group("body").strip() + "\n"
        themed_source, source_evidence = validate_and_theme_dot_source(raw_source, profile_id=profile_id, theme=theme)
        raw_sha = hashlib.sha256(raw_source.encode("utf-8")).hexdigest()
        digest = raw_sha[:16]
        suffix = output_format.lstrip(".").lower()
        figure_path = asset_dir / f"{render_id}-dot-{index:02d}-{digest}.{suffix}"
        dot_source_path = source_dir / f"{render_id}-dot-{index:02d}-{digest}.dot"
        dot_source_path.write_text(themed_source)
        render_context = {
            "source_path": str(dot_source_path),
            "output_format": suffix,
            "theme": theme,
            "normalized_source_sha256": source_evidence["normalized_source_sha256"],
        }
        actual_renderer(themed_source, figure_path, render_context)
        if not figure_path.exists():
            raise GraphvizRenderError(f"Graphviz renderer did not produce output for diagram {index}: {figure_path}")
        output_sha = _sha256_file(figure_path)
        figure_inventory.append(
            {
                "kind": "graphviz_dot",
                "index": index,
                "path": str(figure_path),
                "source_path": str(original_markdown_path),
                "dot_source_path": str(dot_source_path),
                "digest_sha256": raw_sha,
                "normalized_source_sha256": source_evidence["normalized_source_sha256"],
                "output_sha256": output_sha,
                "output_format": suffix,
                "theme": theme,
                "warnings": source_evidence["warnings"],
                "renderer": source_evidence.get("renderer", {}),
            }
        )
        return f"![Graphviz diagram {index}]({figure_path}){{#fig:graphviz-dot-{index}}}"

    rewritten_text = _GRAPHVIZ_FENCE_RE.sub(replace, text)
    rewritten_source = rewritten_dir / f"{render_id}.graphviz.md"
    rewritten_source.write_text(rewritten_text)
    return GraphvizPreprocessResult(rewritten_source, figure_inventory, theme, True)


def validate_and_theme_dot_source(
    source: str,
    profile_id: str,
    theme: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate DOT source and inject bounded profile-derived defaults."""

    if not isinstance(source, str):
        raise GraphvizRenderError("Graphviz/DOT source must be text.")
    if len(source.encode("utf-8")) > MAX_DOT_SOURCE_BYTES:
        raise GraphvizRenderError(f"Graphviz/DOT source exceeds maximum size of {MAX_DOT_SOURCE_BYTES} bytes.")
    stripped = source.lstrip()
    if not re.match(r"(?is)^(strict\s+)?(di)?graph\b", stripped):
        raise GraphvizRenderError("Graphviz/DOT source must start with graph or digraph.")
    remote = _find_remote_reference(source)
    if remote:
        raise GraphvizRenderError(f"Graphviz/DOT source contains remote reference, disallowed by default: {remote}")
    if "{" not in source:
        raise GraphvizRenderError("Graphviz/DOT source must contain an opening graph body brace.")

    resolved_theme = theme or resolve_profile_chart_theme(profile_id)
    palette = [str(color) for color in resolved_theme.get("palette", []) if isinstance(color, str)]
    tokens = resolved_theme.get("tokens", {}) if isinstance(resolved_theme.get("tokens"), dict) else {}
    primary = _safe_dot_string(palette[0] if palette else str(tokens.get("primary", "#0A3870")))
    secondary = _safe_dot_string(str(tokens.get("secondary", palette[1] if len(palette) > 1 else "#44505A")))
    accent = _safe_dot_string(str(tokens.get("accent", palette[2] if len(palette) > 2 else primary)))
    background = _safe_dot_string(str(tokens.get("background", "transparent")))
    surface = _safe_dot_string(str(tokens.get("surface", "#FFFFFF")))
    text_color = _safe_dot_string(str(tokens.get("text", primary)))

    defaults = (
        "\n  // Optical Foundry generated Graphviz profile defaults.\n"
        "  // Authored graph source is preserved below these bounded defaults.\n"
        f'  graph [bgcolor="{background}", color="{primary}", fontcolor="{text_color}"];\n'
        f'  node [shape="box", style="rounded,filled", color="{primary}", fillcolor="{surface}", fontcolor="{text_color}"];\n'
        f'  edge [color="{secondary}", fontcolor="{accent}"];\n'
    )
    themed = source.replace("{", "{" + defaults, 1)
    evidence = {
        "normalized_source_sha256": hashlib.sha256(themed.encode("utf-8")).hexdigest(),
        "theme": resolved_theme,
        "warnings": [],
        "renderer": {
            "name": GRAPHVIZ_RENDERER_NAME,
            "version": PINNED_GRAPHVIZ_VERSION,
            "mode": "local_cli",
        },
    }
    return themed, evidence


def resolve_graphviz_command() -> list[str]:
    """Resolve a local native Graphviz `dot` command."""

    explicit = os.environ.get("GRAPHVIZ_DOT", "").strip()
    if explicit:
        return [explicit]
    if LOCAL_DOT_BINARY.exists():
        return [str(LOCAL_DOT_BINARY)]
    direct = shutil.which("dot")
    if direct:
        return [direct]
    raise GraphvizRenderError(
        "Graphviz dot unavailable: set GRAPHVIZ_DOT, install the repo-local pinned dot binary, or install dot on PATH."
    )


def render_graphviz_cli(source: str, output_path: Path, render_context: dict[str, Any]) -> None:
    """Render one DOT source through local native Graphviz dot."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_path_value = render_context.get("source_path")
    suffix = str(render_context.get("output_format") or output_path.suffix.lstrip(".") or "svg").lower()
    command_prefix = resolve_graphviz_command()
    with tempfile.TemporaryDirectory(prefix="of_graphviz_") as tmp:
        tmp_path = Path(tmp)
        input_path = Path(source_path_value) if source_path_value else tmp_path / "diagram.dot"
        if not input_path.exists():
            input_path.write_text(source)
        cmd = [*command_prefix, f"-T{suffix}", str(input_path), "-o", str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not output_path.exists():
            raise GraphvizRenderError(f"Graphviz dot failed ({result.returncode}): {result.stderr[-1000:]}")


_GRAPHVIZ_FENCE_RE = re.compile(
    r"^```(?:dot|graphviz)[^\n]*\n(?P<body>.*?)^```\s*$",
    flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _find_remote_reference(source: str) -> str:
    match = re.search(r"https?://[^\s\]\)\}\"]+", source, flags=re.I)
    return match.group(0) if match else ""


def _safe_dot_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').strip()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
