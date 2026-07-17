"""Full Vega chart preprocessing for Optical Foundry Markdown/Pandoc renders.

Vega is treated as a local generated-asset lane: fenced ```vega JSON specs are
validated, lightly themed from the active profile, rendered through local/pinned
vega-cli utilities, rewritten to ordinary Markdown image references, and recorded
in render evidence. Specs are render data, not agent instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
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
from engine.mermaid import resolve_profile_chart_theme

PINNED_VEGA_CLI_PACKAGE = "vega-cli@6.2.0"
MAX_VEGA_SPEC_BYTES = 1_000_000

VegaRendererFn = Callable[[dict[str, Any], Path, dict[str, Any]], None]


@dataclass(frozen=True)
class VegaPreprocessResult:
    """Result of rewriting one Markdown source for Vega generated figures."""

    rewritten_source: Path
    figure_inventory: list[dict[str, Any]]
    theme: dict[str, Any]
    changed: bool


@dataclass(frozen=True)
class VegaRenderError(Exception):
    """Raised when Vega validation or rendering fails."""

    message: str

    def __str__(self) -> str:
        return self.message


def preprocess_vega_blocks(
    markdown_path: Path,
    profile_id: str,
    output_dir: Path,
    render_id: str,
    renderer: VegaRendererFn | None = None,
    output_format: str = "pdf",
    *,
    figure_captions: bool = False,
    figure_numbering: bool = False,
    figure_numbering_section: bool = False,
) -> VegaPreprocessResult:
    """Render Vega fences and rewrite them to Markdown image references.

    Caption/numbering behavior is authored, never invented. A chart with no
    authored caption renders with no visible caption and no reserved caption
    whitespace. Doc-level defaults (``figure_captions``/``figure_numbering``) and
    per-figure fenced attributes (``caption=``/``numbered=``/``#id``/``alt=``)
    control visibility and numbering independently. The Vega spec ``description``
    is retained as accessibility alt text, not auto-exposed as a caption.
    """

    markdown_path = Path(markdown_path)
    original_markdown_path = markdown_path
    output_dir = Path(output_dir).resolve()
    text = markdown_path.read_text()
    frontmatter, _body = _split_frontmatter_and_body(text)
    theme = resolve_profile_chart_theme(profile_id, frontmatter or {})

    matches = list(_VEGA_FENCE_RE.finditer(text))
    if not matches:
        return VegaPreprocessResult(markdown_path, [], theme, False)

    asset_dir = output_dir / "figures" / "vega"
    spec_dir = asset_dir / "specs"
    asset_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)
    rewritten_dir = output_dir / "_preprocessed"
    rewritten_dir.mkdir(parents=True, exist_ok=True)

    actual_renderer = renderer or render_vega_cli
    figure_inventory: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        index = len(figure_inventory) + 1
        attrs = _parse_fence_attributes(match.group("attrs") or "")
        raw_source = match.group("body").strip() + "\n"
        try:
            parsed = json.loads(raw_source)
        except json.JSONDecodeError as exc:
            raise VegaRenderError(f"Vega JSON parse failed at chart {index}: {exc}") from exc
        description = parsed.get("description") if isinstance(parsed, dict) else None
        description = str(description).strip() if isinstance(description, str) else ""
        themed_spec, spec_evidence = validate_and_theme_vega_spec(parsed, profile_id=profile_id, theme=theme)
        raw_sha = hashlib.sha256(raw_source.encode("utf-8")).hexdigest()
        digest = raw_sha[:16]
        suffix = output_format.lstrip(".").lower()
        figure_path = asset_dir / f"{render_id}-vega-{index:02d}-{digest}.{suffix}"
        spec_path = spec_dir / f"{render_id}-vega-{index:02d}-{digest}.json"
        normalized_json = _canonical_json(themed_spec)
        spec_path.write_text(normalized_json + "\n")
        render_context = {
            "spec_path": str(spec_path),
            "output_format": suffix,
            "theme": theme,
            "normalized_spec_sha256": spec_evidence["normalized_spec_sha256"],
        }
        actual_renderer(themed_spec, figure_path, render_context)
        if not figure_path.exists():
            raise VegaRenderError(f"Vega renderer did not produce output for chart {index}: {figure_path}")
        output_sha = _sha256_file(figure_path)

        fig_id = attrs.get("id") or f"fig:vega-{index}"
        alt = attrs["alt"] if attrs.get("alt") is not None else description
        explicit_caption = attrs.get("caption")
        if explicit_caption:
            caption = explicit_caption
        elif figure_captions and description:
            # Only promote the description to a visible caption when the author
            # opts in via figure-captions; otherwise it stays accessibility text.
            caption = description
        else:
            caption = ""
        numbered = attrs["numbered"] if attrs.get("numbered") is not None else figure_numbering

        figure_inventory.append(
            {
                "kind": "vega",
                "index": index,
                "path": str(figure_path),
                "source_path": str(original_markdown_path),
                "spec_path": str(spec_path),
                "digest_sha256": raw_sha,
                "normalized_spec_sha256": spec_evidence["normalized_spec_sha256"],
                "output_sha256": output_sha,
                "output_format": suffix,
                "theme": theme,
                "caption": caption,
                "numbered": bool(caption) and bool(numbered),
                "alt": alt,
                "fig_id": fig_id,
                "warnings": spec_evidence["warnings"],
                "renderer": spec_evidence.get("renderer", {}),
            }
        )
        return _emit_vega_reference(
            figure_path,
            suffix=suffix,
            fig_id=fig_id,
            caption=caption,
            numbered=bool(numbered),
            alt=alt,
        )

    rewritten_text = _VEGA_FENCE_RE.sub(replace, text)
    rewritten_source = rewritten_dir / f"{render_id}.vega.md"
    rewritten_source.write_text(rewritten_text)
    return VegaPreprocessResult(rewritten_source, figure_inventory, theme, True)


def validate_and_theme_vega_spec(
    spec: dict[str, Any],
    profile_id: str,
    theme: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a full Vega spec and apply bounded profile-derived theme defaults.

    The merge is conservative: profile palette/config fills absent fields without
    overriding author-provided values.
    """

    if not isinstance(spec, dict):
        raise VegaRenderError("Vega spec must be a JSON object.")
    canonical_input = _canonical_json(spec)
    if len(canonical_input.encode("utf-8")) > MAX_VEGA_SPEC_BYTES:
        raise VegaRenderError(f"Vega spec exceeds maximum size of {MAX_VEGA_SPEC_BYTES} bytes.")
    schema = spec.get("$schema")
    if schema and not _is_allowed_vega_schema(str(schema)):
        raise VegaRenderError(f"Vega schema is not allowlisted: {schema}")

    remote_urls = _find_remote_urls(spec)
    if remote_urls:
        first = remote_urls[0]
        raise VegaRenderError(f"Vega spec contains remote data URL, disallowed by default: {first}")

    warnings = _expression_warnings(spec)
    resolved_theme = theme or resolve_profile_chart_theme(profile_id)
    themed = copy.deepcopy(spec)
    _inject_vega_theme_defaults(themed, resolved_theme.get("vega", {}))
    normalized = _canonical_json(themed)
    evidence = {
        "normalized_spec_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "theme": resolved_theme,
        "warnings": warnings,
        "renderer": {
            "package": PINNED_VEGA_CLI_PACKAGE,
            "mode": "local_cli",
        },
    }
    return themed, evidence


def resolve_vega_command(output_format: str = "pdf") -> list[str]:
    """Resolve a local Vega CLI command for the requested static output format."""

    suffix = output_format.lstrip(".").lower()
    converter = _converter_for_format(suffix)
    explicit = os.environ.get("VEGA_CLI", "").strip()
    if explicit:
        return [explicit]
    direct = shutil.which(converter)
    if direct:
        return [direct]
    npx = shutil.which("npx")
    if npx:
        # vega-cli exposes converter binaries via npm package bin entries; npm
        # needs `-p` to put the pinned package on PATH before invoking vg2*.
        return [npx, "-y", "-p", PINNED_VEGA_CLI_PACKAGE, converter]
    raise VegaRenderError(
        "Vega CLI unavailable: set VEGA_CLI, install vg2pdf/vg2svg, or install npm/npx for the pinned vega-cli fallback."
    )


def render_vega_cli(spec: dict[str, Any], output_path: Path, render_context: dict[str, Any]) -> None:
    """Render one Vega spec through vega-cli (`vg2pdf`, `vg2svg`, or `vg2png`)."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_format = str(render_context.get("output_format") or output_path.suffix.lstrip(".") or "pdf")
    command_prefix = resolve_vega_command(output_format)
    spec_path_value = render_context.get("spec_path")
    with tempfile.TemporaryDirectory(prefix="of_vega_") as tmp:
        tmp_path = Path(tmp)
        input_path = Path(spec_path_value) if spec_path_value else tmp_path / "chart.vg.json"
        if not input_path.exists():
            input_path.write_text(_canonical_json(spec) + "\n")
        cmd = [*command_prefix, str(input_path), str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not output_path.exists():
            raise VegaRenderError(f"Vega CLI failed ({result.returncode}): {result.stderr[-1000:]}")


_VEGA_FENCE_RE = re.compile(
    r"^```vega(?P<attrs>[^\n]*)\n(?P<body>.*?)^```\s*$",
    flags=re.MULTILINE | re.DOTALL,
)

# Fenced-attribute tokens: `#id`, `key="quoted value"`, or `key=bareword`.
_FENCE_ATTR_TOKEN_RE = re.compile(
    r"""#(?P<id>[A-Za-z0-9_:.-]+)|(?P<key>[A-Za-z_][\w-]*)=(?:"(?P<qval>[^"]*)"|'(?P<sval>[^']*)'|(?P<bval>[^\s}]+))"""
)


def _parse_fence_attributes(raw: str) -> dict[str, Any]:
    """Parse ``{#fig-x caption="..." numbered=false alt="..."}`` fence attrs.

    Returns keys ``id`` (str|None), ``caption`` (str|None), ``alt`` (str|None),
    and ``numbered`` (bool|None). Absent keys are None so callers can fall back
    to document-level defaults.
    """
    result: dict[str, Any] = {"id": None, "caption": None, "alt": None, "numbered": None}
    text = raw.strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    for match in _FENCE_ATTR_TOKEN_RE.finditer(text):
        if match.group("id"):
            result["id"] = match.group("id")
            continue
        key = match.group("key")
        value = match.group("qval")
        if value is None:
            value = match.group("sval")
        if value is None:
            value = match.group("bval")
        if value is None:
            continue
        if key in {"caption", "title"}:
            result["caption"] = value
        elif key == "alt":
            result["alt"] = value
        elif key in {"numbered", "number"}:
            result["numbered"] = value.strip().lower() in {"true", "yes", "on", "1"}
    return result


def _latex_escape_caption(value: str) -> str:
    """Escape LaTeX specials in an authored caption string."""
    out = str(value or "")
    for char, repl in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ):
        out = out.replace(char, repl)
    return out


def _emit_vega_reference(
    figure_path: Path,
    *,
    suffix: str,
    fig_id: str,
    caption: str,
    numbered: bool,
    alt: str,
) -> str:
    """Emit the rewritten reference for one rendered Vega figure.

    - PDF, no caption → raw-LaTeX centered ``\\includegraphics`` (no figure
      environment, no caption slot, no reserved whitespace).
    - PDF, caption present → raw-LaTeX ``figure`` with ``\\caption`` (numbered)
      or ``\\caption*`` (unnumbered) plus a ``\\label``.
    - Non-PDF (svg/png/html) → a Markdown image so alt text survives; the alt
      is the authored caption when present, else the Vega description.
    """
    path_str = str(figure_path)
    if suffix != "pdf":
        alt_text = caption or alt or ""
        return f"![{alt_text}]({path_str}){{#{fig_id}}}\n"
    if not caption:
        return (
            "```{=latex}\n"
            f"\\begin{{center}}\\includegraphics{{{path_str}}}\\end{{center}}\n"
            "```\n"
        )
    caption_cmd = "\\caption" if numbered else "\\caption*"
    return (
        "```{=latex}\n"
        "\\begin{figure}[htbp]\n"
        "\\centering\n"
        f"\\includegraphics{{{path_str}}}\n"
        f"{caption_cmd}{{{_latex_escape_caption(caption)}}}\n"
        f"\\label{{{fig_id}}}\n"
        "\\end{figure}\n"
        "```\n"
    )


def _converter_for_format(output_format: str) -> str:
    suffix = output_format.lstrip(".").lower()
    if suffix not in {"pdf", "svg", "png"}:
        raise VegaRenderError(f"Unsupported Vega output format: {output_format}")
    return f"vg2{suffix}"


def _is_allowed_vega_schema(schema: str) -> bool:
    return bool(re.match(r"^https?://vega\.github\.io/schema/vega/v5(\.json)?$", schema))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _inject_vega_theme_defaults(spec: dict[str, Any], vega_theme: dict[str, Any]) -> None:
    if not isinstance(vega_theme, dict):
        return
    if "background" not in spec and isinstance(vega_theme.get("background"), str):
        spec["background"] = vega_theme["background"]
    config = spec.setdefault("config", {})
    if isinstance(config, dict):
        _deep_fill_missing(config, vega_theme.get("config", {}))
        if isinstance(vega_theme.get("range"), dict):
            range_config = config.setdefault("range", {})
            if isinstance(range_config, dict):
                _deep_fill_missing(range_config, vega_theme["range"])


def _deep_fill_missing(target: dict[str, Any], defaults: Any) -> None:
    if not isinstance(defaults, dict):
        return
    for key, value in defaults.items():
        if key not in target:
            target[key] = copy.deepcopy(value)
        elif isinstance(target[key], dict) and isinstance(value, dict):
            _deep_fill_missing(target[key], value)


def _find_remote_urls(value: Any) -> list[str]:
    urls: list[str] = []

    def walk(node: Any, key: str | None = None) -> None:
        if isinstance(node, dict):
            for child_key, child_value in node.items():
                walk(child_value, str(child_key))
        elif isinstance(node, list):
            for child in node:
                walk(child, key)
        elif key == "url" and isinstance(node, str) and re.match(r"^https?://", node, flags=re.I):
            urls.append(node)

    walk(value)
    return urls


def _expression_warnings(value: Any) -> list[str]:
    paths: list[str] = []
    expression_keys = {"expr", "update", "init", "signal"}

    def walk(node: Any, path: str = "$", key: str | None = None) -> None:
        if isinstance(node, dict):
            for child_key, child_value in node.items():
                child_path = f"{path}.{child_key}"
                if child_key in expression_keys or child_key == "signals":
                    paths.append(child_path)
                walk(child_value, child_path, str(child_key))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]", key)

    walk(value)
    if not paths:
        return []
    unique = sorted(set(paths))
    return [
        "Vega spec contains expression-bearing fields; rendered as inert chart input and recorded for review: "
        + ", ".join(unique[:12])
    ]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
