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
from engine.mermaid import MermaidRenderError, preprocess_mermaid_blocks
from engine.vega import VegaRenderError, preprocess_vega_blocks
from engine.profile_resolver import LOCAL_IMPORT, LATEX40, ResolvedProfile, resolve_profile
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
            plan = self._prepare_mermaid_source(plan, out_dir)
            plan = self._prepare_vega_source(plan, out_dir)
            plan = self._prepare_d2_source(plan, out_dir)
            plan = self._prepare_graphviz_source(plan, out_dir)
        except (MermaidRenderError, VegaRenderError, D2RenderError, GraphvizRenderError) as exc:
            elapsed = time.monotonic() - start
            return self._evidence_error(
                plan, out_dir / f"{plan.render_id}{plan.output_extension}", evidence_file, elapsed, str(exc), ["generated-figure-preprocessor"]
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

        # page geometry
        if plan.page_size and plan.page_size != "letter":
            cmd += ["--metadata", f"papersize:{plan.page_size}"]

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

        # --- evidence ---
        evidence = {
            "schema_version": "render_evidence_v1",
            "render_id": plan.render_id,
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
            "warnings": list(plan.boundary_assertions.get("warnings", [])) + defaults_meta.get("warnings", []) + resolved_profile.warnings,
            "boundary": {
                "target_40_latex_mutated": False,
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
        """Resolve an explicit plan template using the same local-first order."""
        template_path = Path(template)
        if template_path.is_absolute():
            return template_path
        local = LOCAL_IMPORT / "templates" / template
        if local.exists():
            return local
        remote = LATEX40 / "templates" / template
        if remote.exists():
            return remote
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

    def _evidence_error(
        self, plan, output_pdf, evidence_file, elapsed, message, cmd
    ) -> dict[str, Any]:
        evidence = {
            "schema_version": "render_evidence_v1",
            "render_id": plan.render_id,
            "status": "error",
            "error": message,
            "command": " ".join(cmd),
            "render_duration_ms": int(elapsed * 1000),
        }
        evidence_file.write_text(json.dumps(evidence, indent=2) + "\n")
        return evidence
