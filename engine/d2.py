"""D2 architecture/system diagram preprocessing for Optical Foundry renders.

D2 is treated as a local generated-asset lane: fenced ```d2 diagrams are
validated, lightly wrapped with profile-derived style variables, rendered through
a local/pinned D2 CLI, rewritten to ordinary Markdown image references, and
recorded in render evidence. D2 source is render data, not agent instructions.
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

PINNED_D2_VERSION = "0.7.1"
LOCAL_D2_BINARY = Path(__file__).resolve().parents[1] / ".tools" / "d2" / f"v{PINNED_D2_VERSION}" / "d2"
MAX_D2_SOURCE_BYTES = 500_000

D2RendererFn = Callable[[str, Path, dict[str, Any]], None]


@dataclass(frozen=True)
class D2PreprocessResult:
    """Result of rewriting one Markdown source for D2 generated figures."""

    rewritten_source: Path
    figure_inventory: list[dict[str, Any]]
    theme: dict[str, Any]
    changed: bool


@dataclass(frozen=True)
class D2RenderError(Exception):
    """Raised when D2 validation or rendering fails."""

    message: str

    def __str__(self) -> str:
        return self.message


def preprocess_d2_blocks(
    markdown_path: Path,
    profile_id: str,
    output_dir: Path,
    render_id: str,
    renderer: D2RendererFn | None = None,
    output_format: str = "svg",
) -> D2PreprocessResult:
    """Render D2 fences and rewrite them to Markdown image references."""

    markdown_path = Path(markdown_path)
    original_markdown_path = markdown_path
    output_dir = Path(output_dir).resolve()
    text = markdown_path.read_text()
    frontmatter, _body = _split_frontmatter_and_body(text)
    theme = resolve_profile_chart_theme(profile_id, frontmatter or {})

    matches = list(_D2_FENCE_RE.finditer(text))
    if not matches:
        return D2PreprocessResult(markdown_path, [], theme, False)

    asset_dir = output_dir / "figures" / "d2"
    source_dir = asset_dir / "sources"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    rewritten_dir = output_dir / "_preprocessed"
    rewritten_dir.mkdir(parents=True, exist_ok=True)

    actual_renderer = renderer or render_d2_cli
    figure_inventory: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        index = len(figure_inventory) + 1
        raw_source = match.group("body").strip() + "\n"
        themed_source, source_evidence = validate_and_theme_d2_source(raw_source, profile_id=profile_id, theme=theme)
        raw_sha = hashlib.sha256(raw_source.encode("utf-8")).hexdigest()
        digest = raw_sha[:16]
        suffix = output_format.lstrip(".").lower()
        figure_path = asset_dir / f"{render_id}-d2-{index:02d}-{digest}.{suffix}"
        d2_source_path = source_dir / f"{render_id}-d2-{index:02d}-{digest}.d2"
        d2_source_path.write_text(themed_source)
        render_context = {
            "source_path": str(d2_source_path),
            "output_format": suffix,
            "theme": theme,
            "normalized_source_sha256": source_evidence["normalized_source_sha256"],
        }
        actual_renderer(themed_source, figure_path, render_context)
        if not figure_path.exists():
            raise D2RenderError(f"D2 renderer did not produce output for diagram {index}: {figure_path}")
        output_sha = _sha256_file(figure_path)
        figure_inventory.append(
            {
                "kind": "d2",
                "index": index,
                "path": str(figure_path),
                "source_path": str(original_markdown_path),
                "d2_source_path": str(d2_source_path),
                "digest_sha256": raw_sha,
                "normalized_source_sha256": source_evidence["normalized_source_sha256"],
                "output_sha256": output_sha,
                "output_format": suffix,
                "theme": theme,
                "warnings": source_evidence["warnings"],
                "renderer": source_evidence.get("renderer", {}),
            }
        )
        return f"![D2 diagram {index}]({figure_path}){{#fig:d2-{index}}}"

    rewritten_text = _D2_FENCE_RE.sub(replace, text)
    rewritten_source = rewritten_dir / f"{render_id}.d2.md"
    rewritten_source.write_text(rewritten_text)
    return D2PreprocessResult(rewritten_source, figure_inventory, theme, True)


def validate_and_theme_d2_source(
    source: str,
    profile_id: str,
    theme: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate D2 source and prepend bounded profile-derived variables.

    The wrapper preserves authored source: style variables are prepended as D2
    variables, not used to rewrite edges/nodes or interpret content.
    """

    if not isinstance(source, str):
        raise D2RenderError("D2 source must be text.")
    if len(source.encode("utf-8")) > MAX_D2_SOURCE_BYTES:
        raise D2RenderError(f"D2 source exceeds maximum size of {MAX_D2_SOURCE_BYTES} bytes.")
    remote = _find_remote_reference(source)
    if remote:
        raise D2RenderError(f"D2 source contains remote reference, disallowed by default: {remote}")

    resolved_theme = theme or resolve_profile_chart_theme(profile_id)
    palette = [str(color) for color in resolved_theme.get("palette", []) if isinstance(color, str)]
    tokens = resolved_theme.get("tokens", {}) if isinstance(resolved_theme.get("tokens"), dict) else {}
    primary = _safe_d2_string(palette[0] if palette else str(tokens.get("primary", "#0A3870")))
    secondary = _safe_d2_string(str(tokens.get("secondary", palette[1] if len(palette) > 1 else "#44505A")))
    accent = _safe_d2_string(str(tokens.get("accent", palette[2] if len(palette) > 2 else primary)))
    background = _safe_d2_string(str(tokens.get("background", "#FFFFFF")))
    wrapper = (
        "# Optical Foundry generated D2 profile variables.\n"
        "# Authored diagram source begins after the boundary marker below.\n"
        "vars: {\n"
        f"  d2-primary: \"{primary}\"\n"
        f"  d2-secondary: \"{secondary}\"\n"
        f"  d2-accent: \"{accent}\"\n"
        f"  d2-background: \"{background}\"\n"
        "}\n"
        "# --- authored D2 source ---\n"
    )
    themed = wrapper + source
    evidence = {
        "normalized_source_sha256": hashlib.sha256(themed.encode("utf-8")).hexdigest(),
        "theme": resolved_theme,
        "warnings": [],
        "renderer": {
            "name": "d2",
            "version": PINNED_D2_VERSION,
            "mode": "local_cli",
        },
    }
    return themed, evidence


def resolve_d2_command() -> list[str]:
    """Resolve a local D2 CLI command.

    Resolution order intentionally avoids remote execution:
    D2_CLI env override, repo-local pinned binary, then a PATH binary.
    """

    explicit = os.environ.get("D2_CLI", "").strip()
    if explicit:
        return [explicit]
    if LOCAL_D2_BINARY.exists():
        return [str(LOCAL_D2_BINARY)]
    direct = shutil.which("d2")
    if direct:
        return [direct]
    raise D2RenderError(
        "D2 CLI unavailable: set D2_CLI, install the repo-local pinned D2 binary, or install d2 on PATH."
    )


def render_d2_cli(source: str, output_path: Path, render_context: dict[str, Any]) -> None:
    """Render one D2 source through the local D2 CLI."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_path_value = render_context.get("source_path")
    command_prefix = resolve_d2_command()
    with tempfile.TemporaryDirectory(prefix="of_d2_") as tmp:
        tmp_path = Path(tmp)
        input_path = Path(source_path_value) if source_path_value else tmp_path / "diagram.d2"
        if not input_path.exists():
            input_path.write_text(source)
        cmd = [*command_prefix, str(input_path), str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not output_path.exists():
            raise D2RenderError(f"D2 CLI failed ({result.returncode}): {result.stderr[-1000:]}")


_D2_FENCE_RE = re.compile(
    r"^```d2[^\n]*\n(?P<body>.*?)^```\s*$",
    flags=re.MULTILINE | re.DOTALL,
)


def _find_remote_reference(source: str) -> str:
    match = re.search(r"https?://[^\s\]\)\}\"]+", source, flags=re.I)
    return match.group(0) if match else ""


def _safe_d2_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').strip()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
