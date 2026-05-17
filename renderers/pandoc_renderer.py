"""Pandoc render dispatch.

Takes a ProjectionPlan and executes it through Pandoc, writing the rendered
artifact and a render evidence JSON sidecar. References 40_latex templates,
styles, and defaults as read-only inputs. Does not mutate 40_latex.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from engine.d2 import D2RenderError, preprocess_d2_blocks
from engine.graphviz import GraphvizRenderError, preprocess_graphviz_blocks
from engine.layout_images import LayoutImageRenderError, preprocess_layout_image_blocks
from engine.mermaid import MermaidRenderError, preprocess_mermaid_blocks
from engine.vega import VegaRenderError, preprocess_vega_blocks
from engine.page_size import (
    collect_profile_classoption,
    collect_profile_geometry,
    merge_page_size_classoption,
    merge_page_size_geometry,
    normalize_page_size,
)
from engine.profile_resolver import LOCAL_IMPORT, ResolvedProfile, resolve_profile
from engine.projection_plan import ProjectionPlan
from renderers.base import Renderer


class PandocRenderer(Renderer):
    """Execute a ProjectionPlan through Pandoc.

    Builds the `pandoc` command line from the plan's Pandoc defaults overlay,
    profile_id hint, template, and style. Shells out to Pandoc and captures
    evidence.
    """

    name = "pandoc"

    def render(self, plan: ProjectionPlan, output_dir: str | None = None) -> dict[str, Any]:
        start = time.monotonic()
        out_dir = (Path(output_dir) if output_dir else Path.cwd()).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pdf = out_dir / f"{plan.render_id}{plan.output_extension}"
        log_file = out_dir / f"{plan.render_id}.log"
        evidence_file = out_dir / f"{plan.render_id}.evidence.json"
        text_file = out_dir / f"{plan.render_id}.txt"

        # --- build pandoc command ---
        try:
            plan = self._prepare_layout_image_source(plan, out_dir)
            plan = self._prepare_mermaid_source(plan, out_dir)
            plan = self._prepare_vega_source(plan, out_dir)
            plan = self._prepare_d2_source(plan, out_dir)
            plan = self._prepare_graphviz_source(plan, out_dir)
        except (LayoutImageRenderError, MermaidRenderError, VegaRenderError, D2RenderError, GraphvizRenderError) as exc:
            elapsed = time.monotonic() - start
            return self._evidence_error(
                plan, out_dir / f"{plan.render_id}{plan.output_extension}", evidence_file, elapsed, str(exc), ["source-preprocessor"]
            )

        render_source = plan.render_source.resolve()

        # profile defaults/template/resource environment: single-object profile
        # resolution is centralized in engine.profile_resolver. Manifest-family
        # assembly decisions remain outside this renderer.
        resolved_profile = resolve_profile(plan.profile_id)
        cmd_source = self._stationery_normalized_source(
            render_source, out_dir, plan.render_id, resolved_profile.profile_family
        )
        cmd_source = self._titlepage_background_normalized_source(cmd_source, out_dir, plan.render_id)
        cmd = ["pandoc", str(cmd_source), "-o", str(output_pdf)]
        defaults_meta: dict[str, Any] = {}
        for defaults_file in resolved_profile.defaults_stack:
            cmd += ["--defaults", str(defaults_file)]
            defaults_meta = self._merge_defaults_metadata(defaults_meta, self._read_defaults_metadata(defaults_file))
        frontmatter_variables_defaults = self._frontmatter_variables_defaults(cmd_source, out_dir, plan.render_id)
        if frontmatter_variables_defaults is not None:
            cmd += ["--defaults", str(frontmatter_variables_defaults)]
        page_geometry_defaults = self._page_geometry_defaults(plan, resolved_profile, out_dir)
        page_geometry_options = self._page_geometry_options(plan, resolved_profile)
        if page_geometry_defaults is not None:
            cmd += ["--defaults", str(page_geometry_defaults)]

        # template — prefer explicit plan override, otherwise resolved profile
        if plan.template:
            template_path = self._resolve_template_override(plan.template)
        else:
            template_path = resolved_profile.template_path
        template = template_path.name if template_path else ""
        if template_path and template_path.exists():
            cmd += ["--template", str(template_path)]

        # metadata
        if plan.title:
            cmd += ["--metadata", f"title={plan.title}"]
        if plan.subtitle:
            cmd += ["--metadata", f"subtitle={plan.subtitle}"]
        if plan.author:
            cmd += ["--metadata", f"author={plan.author}"]
        if plan.date:
            cmd += ["--metadata", f"date={plan.date}"]
        # Pandoc's --toc flag is the source of truth for TOC ownership.
        # 40_latex templates render their \tableofcontents blocks behind
        # Pandoc's $if(toc)$ guard, so skipping --toc suppresses TOC entirely.
        if plan.toc:
            cmd += ["--toc", "--toc-depth", str(plan.toc_depth)]
        if plan.numbersections:
            cmd += ["--number-sections"]

        # tex engine
        # Preserve the engine selected by the profile defaults stack. The legacy
        # Johannah-letter lane uses lualatex; forcing xelatex changes the output
        # metrics and breaks render parity.
        pdf_engine = self._resolved_pdf_engine(resolved_profile.defaults_stack)
        xe = shutil.which(pdf_engine) or pdf_engine
        cmd += [
            "--pdf-engine", str(xe),
            "--pdf-engine-opt=-interaction=nonstopmode",
            "--pdf-engine-opt=-halt-on-error",
        ]

        env = os.environ.copy()
        env.update(resolved_profile.render_environment.env_overrides())

        for resource_path in resolved_profile.render_environment.resource_paths:
            if resource_path.exists():
                cmd += ["--resource-path", str(resource_path)]

        # Page geometry is lowered through a final defaults overlay so imported
        # templates that rely on `$geometry$` receive both the requested paper
        # size and their existing margin/profile geometry options.

        # --- execute ---
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
                cwd=resolved_profile.render_environment.cwd,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return self._evidence_error(
                plan, output_pdf, evidence_file, elapsed, "pandoc timed out after 300s", cmd
            )

        elapsed = time.monotonic() - start
        success = result.returncode == 0 and output_pdf.exists()

        # log
        log_file.write_text(result.stdout + "\n--- STDERR ---\n" + result.stderr)

        if not success:
            return self._evidence_error(
                plan, output_pdf, evidence_file, elapsed,
                f"pandoc exit {result.returncode}: {result.stderr[-500:]}", cmd
            )

        # --- extract text ---
        try:
            subprocess.run(
                ["pdftotext", str(output_pdf), str(text_file)],
                capture_output=True, timeout=60,
            )
            text_extract = text_file.read_text(errors="replace") if text_file.exists() else ""
        except Exception:
            text_extract = ""

        # --- pdf info ---
        pdf_bytes = output_pdf.stat().st_size
        pdf_sha = self._sha256_file(output_pdf)
        pages = self._count_pages(output_pdf)

        warnings = list(plan.boundary_assertions.get("warnings", [])) + defaults_meta.get("warnings", []) + resolved_profile.warnings
        validation = self._validation_success(
            pdf_written=output_pdf.exists(),
            text_extract=text_extract,
            source_inventory=plan.source_inventory,
            figure_inventory=plan.figure_inventory,
            warnings=warnings,
        )

        # --- evidence ---
        evidence = {
            "schema_version": "render_evidence_v1",
            "render_id": plan.render_id,
            "status": "ok",
            "profile": self._profile_evidence(resolved_profile, template_path),
            "input": {
                "path": str(plan.render_source),
                "digest_sha256": self._sha256_file(plan.render_source),
                "bytes": plan.render_source.stat().st_size,
            },
            "source_inventory": plan.source_inventory,
            "figure_inventory": plan.figure_inventory,
            "assembly": self._assembly_evidence(plan),
            "render_metadata": {
                "profile": plan.profile_id,
                "canonical_profile": resolved_profile.canonical_profile_id,
                "profile_family": resolved_profile.profile_family,
                "template": template,
                "defaults_stack": [str(p) for p in resolved_profile.defaults_stack],
                "command": " ".join(cmd),
                "pandoc_version": self._pandoc_version(),
                "tex_engine": xe,
                "page_geometry_defaults": str(page_geometry_defaults) if page_geometry_defaults else "",
                "page_geometry_options": page_geometry_options,
                "page_margin_options": plan.page_margins if page_geometry_options else [],
                "delivery": plan.delivery,
                "render_duration_ms": int(elapsed * 1000),
                "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "success": success,
            },
            "output": {
                "pdf_path": str(output_pdf),
                "pdf_pages": pages,
                "pdf_bytes": pdf_bytes,
                "pdf_sha256": pdf_sha,
                "page_size": plan.page_size,
            },
            "integrity": {
                "text_extract_exists": bool(text_extract),
                "expected_markers_found": [],
                "all_sources_represented": len(plan.source_inventory) > 0,
                "toc_present": plan.toc,
                "toc_depth": plan.toc_depth,
                "figures_validated": len(plan.figure_inventory) == 0,
            },
            "validation": validation,
            "warnings": warnings,
            "boundary": {
                "target_legacy_profile_tree_mutated": False,
                "production_output": False,
                "packet_local_generated_only": True,
                **resolved_profile.boundary,
                **defaults_meta.get("boundary", {}),
                **plan.boundary_assertions,
            },
            "command": " ".join(cmd),
            "logs": str(log_file),
        }

        evidence_file.write_text(json.dumps(evidence, indent=2) + "\n")
        return evidence

    def _prepare_layout_image_source(
        self,
        plan: ProjectionPlan,
        out_dir: Path,
    ) -> ProjectionPlan:
        """Rewrite optional source-placed layout image blocks before Pandoc.

        This is intentionally opt-in. Ordinary Markdown images keep their normal
        behavior; only fenced `of-image` blocks become wrapfig/TikZ/shipout raw
        LaTeX for PDF profiles.
        """

        if not plan.render_source.exists():
            return plan

        resolved_profile = resolve_profile(plan.profile_id)
        if not self._layout_images_supported(plan, resolved_profile):
            return plan

        result = preprocess_layout_image_blocks(
            plan.render_source,
            out_dir,
            plan.render_id,
            [LOCAL_IMPORT, *resolved_profile.asset_roots, *plan.source_resource_roots],
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
            "layout_image_profile_family": resolved_profile.profile_family,
            "layout_image_canonical_profile": resolved_profile.canonical_profile_id,
            "layout_image_render_mode": "pre_pandoc_raw_latex",
            "layout_image_graphicspath_roots": result.graphicspath_roots,
            "figure_count_by_kind": figure_count_by_kind,
        }
        if layout_image_count:
            updates.update(
                {
                    "layout_images_enabled": True,
                    "layout_image_count": layout_image_count,
                }
            )
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
        return replace(
            plan,
            render_source=result.rewritten_source,
            figure_inventory=[*plan.figure_inventory, *result.figure_inventory],
            boundary_assertions=boundary,
        )

    @staticmethod
    def _layout_images_supported(plan: ProjectionPlan, resolved_profile: ResolvedProfile) -> bool:
        """Return true when `of-image` blocks can safely lower to raw LaTeX."""

        return (
            str(plan.output_format).lower() == "pdf"
            and plan.output_extension == ".pdf"
            and resolved_profile.template_path.suffix.lower() == ".tex"
        )

    def _prepare_mermaid_source(
        self,
        plan: ProjectionPlan,
        out_dir: Path,
        mermaid_renderer=None,
        mermaid_output_format: str = "pdf",
    ) -> ProjectionPlan:
        """Pre-render Mermaid fences and return an updated ProjectionPlan.

        This method is intentionally pre-Pandoc so document renders and manifest
        assembly renders share the same behavior: whatever Markdown source the
        plan points at is scanned, Mermaid fences become generated figures, and
        the final Pandoc pass only sees ordinary image references.
        """

        if not plan.render_source.exists():
            # Preserve the renderer's existing missing-source error semantics;
            # Mermaid preprocessing is only a transform for readable Markdown.
            return plan

        result = preprocess_mermaid_blocks(
            plan.render_source,
            profile_id=plan.profile_id,
            output_dir=out_dir,
            render_id=plan.render_id,
            renderer=mermaid_renderer,
            output_format=mermaid_output_format,
        )
        if not result.changed:
            return plan

        boundary = dict(plan.boundary_assertions)
        figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
        figure_count_by_kind["mermaid"] = figure_count_by_kind.get("mermaid", 0) + len(result.figure_inventory)
        boundary.update(
            {
                "generated_figures_enabled": True,
                "figure_count_by_kind": figure_count_by_kind,
                "mermaid_enabled": True,
                "mermaid_diagram_count": len(result.figure_inventory),
                "mermaid_theme": result.theme,
                "mermaid_render_mode": "pre_pandoc_generated_asset",
            }
        )
        return replace(
            plan,
            render_source=result.rewritten_source,
            figure_inventory=[*plan.figure_inventory, *result.figure_inventory],
            boundary_assertions=boundary,
        )

    def _prepare_vega_source(
        self,
        plan: ProjectionPlan,
        out_dir: Path,
        vega_renderer=None,
        vega_output_format: str = "pdf",
    ) -> ProjectionPlan:
        """Pre-render full Vega fences and return an updated ProjectionPlan."""

        if not plan.render_source.exists():
            return plan

        result = preprocess_vega_blocks(
            plan.render_source,
            profile_id=plan.profile_id,
            output_dir=out_dir,
            render_id=plan.render_id,
            renderer=vega_renderer,
            output_format=vega_output_format,
        )
        if not result.changed:
            return plan

        boundary = dict(plan.boundary_assertions)
        figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
        figure_count_by_kind["vega"] = figure_count_by_kind.get("vega", 0) + len(result.figure_inventory)
        boundary.update(
            {
                "generated_figures_enabled": True,
                "figure_count_by_kind": figure_count_by_kind,
                "vega_enabled": True,
                "vega_chart_count": len(result.figure_inventory),
                "vega_theme": result.theme,
                "vega_render_mode": "pre_pandoc_generated_asset",
            }
        )
        warnings = [warning for fig in result.figure_inventory for warning in fig.get("warnings", [])]
        if warnings:
            boundary["warnings"] = [*list(boundary.get("warnings", [])), *warnings]
        return replace(
            plan,
            render_source=result.rewritten_source,
            figure_inventory=[*plan.figure_inventory, *result.figure_inventory],
            boundary_assertions=boundary,
        )

    def _prepare_d2_source(
        self,
        plan: ProjectionPlan,
        out_dir: Path,
        d2_renderer=None,
        d2_output_format: str = "svg",
    ) -> ProjectionPlan:
        """Pre-render D2 architecture/system diagram fences and return an updated ProjectionPlan."""

        if not plan.render_source.exists():
            return plan

        result = preprocess_d2_blocks(
            plan.render_source,
            profile_id=plan.profile_id,
            output_dir=out_dir,
            render_id=plan.render_id,
            renderer=d2_renderer,
            output_format=d2_output_format,
        )
        if not result.changed:
            return plan

        boundary = dict(plan.boundary_assertions)
        figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
        figure_count_by_kind["d2"] = figure_count_by_kind.get("d2", 0) + len(result.figure_inventory)
        boundary.update(
            {
                "generated_figures_enabled": True,
                "figure_count_by_kind": figure_count_by_kind,
                "d2_enabled": True,
                "d2_diagram_count": len(result.figure_inventory),
                "d2_theme": result.theme,
                "d2_render_mode": "pre_pandoc_generated_asset",
            }
        )
        warnings = [warning for fig in result.figure_inventory for warning in fig.get("warnings", [])]
        if warnings:
            boundary["warnings"] = [*list(boundary.get("warnings", [])), *warnings]
        return replace(
            plan,
            render_source=result.rewritten_source,
            figure_inventory=[*plan.figure_inventory, *result.figure_inventory],
            boundary_assertions=boundary,
        )

    def _prepare_graphviz_source(
        self,
        plan: ProjectionPlan,
        out_dir: Path,
        graphviz_renderer=None,
        graphviz_output_format: str = "svg",
    ) -> ProjectionPlan:
        """Pre-render Graphviz/DOT topology diagram fences and return an updated ProjectionPlan."""

        if not plan.render_source.exists():
            return plan

        result = preprocess_graphviz_blocks(
            plan.render_source,
            profile_id=plan.profile_id,
            output_dir=out_dir,
            render_id=plan.render_id,
            renderer=graphviz_renderer,
            output_format=graphviz_output_format,
        )
        if not result.changed:
            return plan

        boundary = dict(plan.boundary_assertions)
        figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
        figure_count_by_kind["graphviz_dot"] = figure_count_by_kind.get("graphviz_dot", 0) + len(result.figure_inventory)
        boundary.update(
            {
                "generated_figures_enabled": True,
                "figure_count_by_kind": figure_count_by_kind,
                "graphviz_dot_enabled": True,
                "graphviz_dot_diagram_count": len(result.figure_inventory),
                "graphviz_dot_theme": result.theme,
                "graphviz_dot_render_mode": "pre_pandoc_generated_asset",
            }
        )
        warnings = [warning for fig in result.figure_inventory for warning in fig.get("warnings", [])]
        if warnings:
            boundary["warnings"] = [*list(boundary.get("warnings", [])), *warnings]
        return replace(
            plan,
            render_source=result.rewritten_source,
            figure_inventory=[*plan.figure_inventory, *result.figure_inventory],
            boundary_assertions=boundary,
        )

    # ── helpers ──────────────────────────────

    def _find_profile_defaults(self, profile_id: str) -> Path | None:
        """Compatibility helper: return the final defaults file for a profile.

        New code should use engine.profile_resolver.resolve_profile() directly.
        """
        resolved = resolve_profile(profile_id)
        return resolved.defaults_stack[-1] if resolved.defaults_stack else None

    def _infer_template(self, profile_id: str) -> str | None:
        """Compatibility helper backed by the shared profile resolver."""
        resolved = resolve_profile(profile_id)
        return resolved.template_path.name if resolved.template_path else None

    def _resolve_template_override(self, template: str) -> Path:
        """Resolve an explicit plan template from Foundry-owned profile imports."""
        template_path = Path(template)
        if template_path.is_absolute():
            return template_path
        local = LOCAL_IMPORT / "templates" / template
        return local

    @staticmethod
    def _merge_defaults_metadata(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        merged = {
            "warnings": list(left.get("warnings", [])) + list(right.get("warnings", [])),
            "boundary": {**left.get("boundary", {}), **right.get("boundary", {})},
        }
        return merged

    @staticmethod
    def _profile_evidence(resolved: ResolvedProfile, template_path: Path | None) -> dict[str, Any]:
        return {
            "profile_id": resolved.profile_id,
            "canonical_profile_id": resolved.canonical_profile_id,
            "profile_family": resolved.profile_family,
            "defaults_stack": [str(p) for p in resolved.defaults_stack],
            "template_path": str(template_path) if template_path else "",
            "asset_roots": [str(p) for p in resolved.asset_roots],
            "font_policy": resolved.font_policy,
            "environment": {
                "TEXMFHOME": str(resolved.render_environment.texmfhome) if resolved.render_environment.texmfhome else "",
                "TEXINPUTS": resolved.render_environment.texinputs,
                "resource_paths": [str(p) for p in resolved.render_environment.resource_paths],
            },
            "boundary": resolved.boundary,
        }

    @staticmethod
    def _assembly_evidence(plan: ProjectionPlan) -> dict[str, Any]:
        if plan.assembly is None:
            return {}
        return {
            "assembly_kind": plan.assembly.assembly_kind,
            "schema_version": plan.assembly.schema_version,
            "manifest_family": plan.assembly.manifest_family,
            "manifest_subtype": plan.assembly.manifest_subtype,
            "assembly_strategy": plan.assembly.assembly_strategy,
            "numbering_strategy": plan.assembly.numbering_strategy,
            "assembly_title": plan.assembly.assembly_title,
            "source_order": plan.assembly.source_order,
            "source_roles": plan.assembly.source_roles,
            "child_profiles": plan.assembly.child_profiles,
        }

    @staticmethod
    def _read_defaults_metadata(path: Path) -> dict[str, Any]:
        """Read small OF-local metadata hints from defaults YAML.

        Currently used for local placeholder asset warnings so synthetic renders
        cannot be mistaken for production outputs.
        """
        try:
            import yaml
            data = yaml.safe_load(path.read_text()) or {}
        except Exception:
            return {}
        vars_ = data.get("variables", {}) if isinstance(data, dict) else {}
        out: dict[str, Any] = {"warnings": [], "boundary": {}}
        if isinstance(vars_, dict) and vars_.get("placeholder_assets") is True:
            note = vars_.get("placeholder_asset_note", "Synthetic placeholder assets active.")
            out["warnings"].append(str(note))
            out["boundary"]["placeholder_assets"] = True
        return out

    @staticmethod
    def _stationery_normalized_source(
        render_source: Path, out_dir: Path, render_id: str, profile_family: str
    ) -> Path:
        """Return a render-only Markdown copy with duplicate salutation removed.

        Atrium letter sources often keep `variables.opening` for templates while
        also keeping the salutation in body Markdown for source readability. The
        imported Johannah stationery template renders `opening` itself, so the
        first body line must be removed only for the render copy when it matches
        the template opening exactly. The canonical source is not modified.
        """
        if profile_family != "stationery_art" or not render_source.exists():
            return render_source
        text = render_source.read_text(encoding="utf-8", errors="ignore")
        if not text.startswith("---\n"):
            return render_source
        end = text.find("\n---", 4)
        if end == -1:
            return render_source
        frontmatter_raw = text[4:end]
        body = text[end + 4:]
        try:
            import yaml
            frontmatter = yaml.safe_load(frontmatter_raw) or {}
        except Exception:
            return render_source
        if not isinstance(frontmatter, dict):
            return render_source
        variables = frontmatter.get("variables", {})
        if not isinstance(variables, dict):
            return render_source
        opening = variables.get("opening") or frontmatter.get("opening")
        if not isinstance(opening, str) or not opening.strip():
            return render_source

        def _plain_markdown_line(line: str) -> str:
            plain = line.strip()
            # Salutations are sometimes kept source-readable as **My love,**
            # while the template variable is unadorned. Compare the textual
            # value, not the Markdown emphasis wrapper.
            plain = re.sub(r"^([*_`]+)(.*)\1$", r"\2", plain).strip()
            return plain

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
        normalized = text[: end + 4] + normalized_body
        path = out_dir / f"{render_id}.stationery_source.md"
        path.write_text(normalized, encoding="utf-8")
        return path

    @staticmethod
    def _resolved_pdf_engine(defaults_stack: list[Path]) -> str:
        """Return the last pdf-engine declared by the defaults stack.

        Legacy 40_latex lets profile defaults choose the engine. Personal-letter
        profiles intentionally switch from the yugen base xelatex default to
        lualatex; forcing xelatex in Foundry changes output metrics and breaks
        visual parity.
        """
        engine = "xelatex"
        try:
            import yaml
        except Exception:
            return engine
        for defaults_file in defaults_stack:
            try:
                data = yaml.safe_load(defaults_file.read_text()) or {}
            except Exception:
                continue
            if isinstance(data, dict) and data.get("pdf-engine"):
                engine = str(data["pdf-engine"])
        return engine

    @staticmethod
    def _page_geometry_options(plan: ProjectionPlan, resolved_profile: ResolvedProfile) -> list[str]:
        """Return final geometry options for the requested page size.

        The imported 40_latex templates use `$geometry$` rather than Pandoc's
        default `$papersize$` documentclass plumbing. To make page-size overrides
        reliable across those templates, lower the semantic page size into
        geometry-package options while preserving non-paper geometry such as
        margins from the resolved profile defaults stack.
        """

        page_size = normalize_page_size(plan.page_size)
        if resolved_profile.profile_family != "document_spine":
            return []
        if page_size == "letter" and not plan.page_margins:
            return []
        existing_geometry = collect_profile_geometry(resolved_profile.defaults_stack)
        return merge_page_size_geometry(page_size, existing_geometry, plan.page_margins)

    @staticmethod
    def _page_geometry_defaults(plan: ProjectionPlan, resolved_profile: ResolvedProfile, out_dir: Path) -> Path | None:
        """Materialize page-size geometry as the final Pandoc defaults overlay.

        Geometry options alone update TeX layout dimensions in the imported
        memoir templates, but XeTeX can still emit a letter MediaBox unless the
        paper special is emitted after geometry establishes ``\\paperwidth`` and
        ``\\paperheight``. Lower the physical page assertion through
        ``header-includes`` so this remains a render-only overlay instead of a
        local profile/template mutation.
        """

        geometry = PandocRenderer._page_geometry_options(plan, resolved_profile)
        if not geometry:
            return None
        path = out_dir / f"{plan.render_id}.page_geometry.yaml"
        import yaml
        header_includes = [
            *PandocRenderer._source_header_includes(plan.render_source),
            r"\special{papersize=\the\paperwidth,\the\paperheight}",
        ]
        variables: dict[str, Any] = {
            "geometry": geometry,
            "header-includes": list(dict.fromkeys(header_includes)),
        }
        if plan.delivery.get("mode") == "bound":
            variables["header-includes"] = list(
                dict.fromkeys([*variables["header-includes"], *PandocRenderer._bound_delivery_header_includes(plan)])
            )
            if plan.delivery.get("page_numbers") == "outer":
                variables["pagestyle"] = "ofBoundOuter"
            if plan.delivery.get("footer_metadata", {}).get("suppress_repeated", False):
                variables["footeremail"] = ""
        existing_classoption = collect_profile_classoption(resolved_profile.defaults_stack)
        classoption = merge_page_size_classoption(plan.page_size, existing_classoption)
        if plan.delivery.get("mode") == "bound" and plan.delivery.get("duplex") is True:
            classoption = [option for option in classoption if str(option).lower() != "oneside"]
            if not any(str(option).lower() == "twoside" for option in classoption):
                classoption.insert(max(len(classoption) - 1, 0), "twoside")
        if classoption:
            variables["classoption"] = classoption
        payload = {"variables": variables}
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return path

    @staticmethod
    def _bound_delivery_header_includes(plan: ProjectionPlan) -> list[str]:
        if plan.delivery.get("mode") != "bound":
            return []
        includes: list[str] = []
        if plan.delivery.get("page_numbers") == "outer":
            running_headers = plan.delivery.get("running_headers", {})
            headers_enabled = bool(running_headers.get("enabled")) if isinstance(running_headers, dict) else False
            header_source = str(running_headers.get("source", "chapter")) if isinstance(running_headers, dict) else "chapter"
            suppress_on = set(running_headers.get("suppress_on", [])) if isinstance(running_headers, dict) else set()
            even_head, odd_head = PandocRenderer._bound_running_header_cells(
                enabled=headers_enabled,
                source=header_source,
                title=plan.title,
            )
            plain_alias = "ofBoundPlain" if headers_enabled and "chapter_openers" in suppress_on else "ofBoundOuter"
            includes.append(
                "\\makeatletter\n"
                "\\@ifclassloaded{memoir}{%\n"
                "  \\makepagestyle{ofBoundOuter}\n"
                f"  \\makeevenhead{{ofBoundOuter}}{{{even_head}}}{{}}{{}}\n"
                f"  \\makeoddhead {{ofBoundOuter}}{{}}{{}}{{{odd_head}}}\n"
                "  \\makeevenfoot{ofBoundOuter}{\\thepage}{}{}\n"
                "  \\makeoddfoot {ofBoundOuter}{}{}{\\thepage}\n"
                "  \\makepagestyle{ofBoundPlain}\n"
                "  \\makeevenhead{ofBoundPlain}{}{}{}\n"
                "  \\makeoddhead {ofBoundPlain}{}{}{}\n"
                "  \\makeevenfoot{ofBoundPlain}{\\thepage}{}{}\n"
                "  \\makeoddfoot {ofBoundPlain}{}{}{\\thepage}\n"
                f"  \\aliaspagestyle{{plain}}{{{plain_alias}}}\n"
                "}{}\n"
                "\\makeatother"
            )
        return includes

    @staticmethod
    def _bound_running_header_cells(*, enabled: bool, source: str, title: str) -> tuple[str, str]:
        if not enabled:
            return "", ""
        source = source.strip().lower().replace("-", "_").replace(" ", "_")
        if source == "document_title":
            escaped = PandocRenderer._latex_header_text(title)
            return rf"\small\itshape {escaped}" if escaped else "", rf"\small\itshape {escaped}" if escaped else ""
        if source == "section":
            return r"\small\itshape\rightmark", r"\small\itshape\rightmark"
        return r"\small\itshape\leftmark", r"\small\itshape\rightmark"

    @staticmethod
    def _latex_header_text(value: str) -> str:
        return str(value or "").replace("\\", r"\\").replace("&", r"\&").replace("%", r"\%").replace("#", r"\#").replace("_", r"\_").strip()

    @staticmethod
    def _source_header_includes(render_source: Path) -> list[str]:
        if not render_source.exists():
            return []
        text = render_source.read_text(encoding="utf-8", errors="ignore")
        if not text.startswith("---\n"):
            return []
        end = text.find("\n---", 4)
        if end == -1:
            return []
        try:
            import yaml
            frontmatter = yaml.safe_load(text[4:end]) or {}
        except Exception:
            return []
        if not isinstance(frontmatter, dict):
            return []
        includes = frontmatter.get("header-includes") or frontmatter.get("header_includes")
        if includes is None:
            return []
        if isinstance(includes, list):
            return [str(item) for item in includes if item]
        return [str(includes)] if includes else []

    @staticmethod
    def _titlepage_background_normalized_source(render_source: Path, out_dir: Path, render_id: str) -> Path:
        """Return a render-only copy with unsafe title-page background paths removed.

        Direct Markdown sources can expose Pandoc template variables through
        top-level YAML metadata or through nested `variables:`. Because
        `titlepage_background_image` is interpolated into a LaTeX
        `\\includegraphics` path, keep only relative PNG/JPG/PDF resource paths
        and strip unsafe values from the render copy without mutating the source.
        """
        if not render_source.exists():
            return render_source
        text = render_source.read_text(encoding="utf-8", errors="ignore")
        if not text.startswith("---\n"):
            return render_source
        end = text.find("\n---", 4)
        if end == -1:
            return render_source
        frontmatter_raw = text[4:end]
        body = text[end + 4:]
        try:
            import yaml
            frontmatter = yaml.safe_load(frontmatter_raw) or {}
        except Exception:
            return render_source
        if not isinstance(frontmatter, dict):
            return render_source

        changed = False
        if "titlepage_background_image" in frontmatter and not PandocRenderer._safe_frontmatter_resource_path(
            frontmatter.get("titlepage_background_image")
        ):
            frontmatter.pop("titlepage_background_image", None)
            changed = True

        variables = frontmatter.get("variables")
        if isinstance(variables, dict) and "titlepage_background_image" in variables:
            if not PandocRenderer._safe_frontmatter_resource_path(variables.get("titlepage_background_image")):
                variables = dict(variables)
                variables.pop("titlepage_background_image", None)
                frontmatter["variables"] = variables
                changed = True

        if not changed:
            return render_source

        path = out_dir / f"{render_id}.titlepage_guarded.md"
        import yaml
        fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip()
        path.write_text(f"---\n{fm_yaml}\n---{body}", encoding="utf-8")
        return path

    @staticmethod
    def _frontmatter_variables_defaults(render_source: Path, out_dir: Path, render_id: str) -> Path | None:
        """Materialize nested frontmatter `variables:` as a final defaults file.

        40_latex promotes simple source-frontmatter variables into Pandoc
        template variables after the profile defaults stack. Foundry needs the
        same behavior for letter profiles so fields such as `opening`,
        `penned_date`, and `signature_name` reach the imported templates without
        mutating the Atrium source.
        """
        if not render_source.exists():
            return None
        text = render_source.read_text(encoding="utf-8", errors="ignore")
        if not text.startswith("---\n"):
            return None
        end = text.find("\n---", 4)
        if end == -1:
            return None
        try:
            import yaml
            frontmatter = yaml.safe_load(text[4:end]) or {}
        except Exception:
            return None
        if not isinstance(frontmatter, dict):
            return None
        variables = frontmatter.get("variables")
        if not isinstance(variables, dict) or not variables:
            return None
        body = text[end + 4:]
        nonempty_body_lines = [line.strip() for line in body.splitlines() if line.strip()]
        manual_closing = ""
        manual_signature = ""
        if len(nonempty_body_lines) >= 2 and nonempty_body_lines[-1] in {"Luis", "Luis E. Ramirez"}:
            candidate_closing = nonempty_body_lines[-2]
            if candidate_closing.startswith("With ") or candidate_closing.endswith(","):
                manual_closing = candidate_closing
                manual_signature = nonempty_body_lines[-1]
        safe_variables = {}
        for key, value in variables.items():
            if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
                continue
            if key == "titlepage_background_image" and not PandocRenderer._safe_frontmatter_resource_path(value):
                continue
            # If the body already carries a manual signoff, render that signoff
            # through the stationery template instead of appending the default
            # `signature_name` after a second body-level signature.
            if key in {"closing", "signature_name"} and manual_signature:
                continue
            if isinstance(value, str):
                value = value.replace("\\", "\\\\").replace("#", "\\#")
            safe_variables[str(key)] = value
        if manual_signature:
            safe_variables["closing"] = manual_closing.replace("\\", "\\\\").replace("#", "\\#")
            safe_variables["signature_name"] = manual_signature.replace("\\", "\\\\").replace("#", "\\#")
        if not safe_variables:
            return None
        path = out_dir / f"{render_id}.frontmatter_variables.yaml"
        import yaml
        path.write_text(yaml.safe_dump({"variables": safe_variables}, sort_keys=False), encoding="utf-8")
        return path

    @staticmethod
    def _safe_frontmatter_resource_path(value: Any) -> bool:
        if not isinstance(value, str) or not value.strip() or "\x00" in value or "://" in value:
            return False
        if any(ch in value for ch in ("{", "}", "$", "`")):
            return False
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            return False
        return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf"}

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _count_pages(pdf_path: Path) -> int:
        try:
            import re
            info = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True)
            m = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
            return int(m.group(1)) if m else 0
        except Exception:
            return 0

    @staticmethod
    def _pandoc_version() -> str:
        try:
            return subprocess.check_output(["pandoc", "--version"], text=True).splitlines()[0]
        except Exception:
            return "unknown"

    @staticmethod
    def _raw_latex_leakage(text_extract: str) -> bool:
        """Return true when extracted PDF text appears to expose raw render syntax."""
        if not text_extract:
            return False
        return bool(
            re.search(
                r"(?:```of-[a-z-]+|\\(?:begin|end|usepackage|includegraphics|OF[A-Za-z]+))",
                text_extract,
            )
        )

    def _validation_success(
        self,
        *,
        pdf_written: bool,
        text_extract: str,
        source_inventory: list[dict[str, Any]],
        figure_inventory: list[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        checks = {
            "pdf_written": pdf_written,
            "text_extract_exists": bool(text_extract),
            "all_sources_represented": len(source_inventory) > 0,
            "figure_inventory_recorded": isinstance(figure_inventory, list),
            "raw_latex_leakage": self._raw_latex_leakage(text_extract),
        }
        passed = (
            checks["pdf_written"]
            and checks["text_extract_exists"]
            and checks["all_sources_represented"]
            and checks["figure_inventory_recorded"]
            and not checks["raw_latex_leakage"]
        )
        return {
            "status": "passed" if passed else "failed",
            "checks": checks,
            "warning_count": len(warnings),
            "errors": [],
        }

    @staticmethod
    def _validation_error(message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "checks": {
                "pdf_written": False,
                "text_extract_exists": False,
                "all_sources_represented": False,
                "figure_inventory_recorded": False,
                "raw_latex_leakage": False,
            },
            "warning_count": 0,
            "errors": [message],
        }

    def _evidence_error(
        self, plan, output_pdf, evidence_file, elapsed, message, cmd
    ) -> dict[str, Any]:
        evidence = {
            "schema_version": "render_evidence_v1",
            "render_id": plan.render_id,
            "status": "error",
            "error": message,
            "validation": self._validation_error(message),
            "command": " ".join(cmd),
            "render_duration_ms": int(elapsed * 1000),
        }
        evidence_file.write_text(json.dumps(evidence, indent=2) + "\n")
        return evidence
