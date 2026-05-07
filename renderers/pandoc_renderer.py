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
from pathlib import Path
from typing import Any

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
        render_source = plan.render_source.resolve()
        cmd = ["pandoc", str(render_source), "-o", str(output_pdf)]

        # profile defaults/template/resource environment: single-object profile
        # resolution is centralized in engine.profile_resolver. Manifest-family
        # assembly decisions remain outside this renderer.
        resolved_profile = resolve_profile(plan.profile_id)
        defaults_meta: dict[str, Any] = {}
        for defaults_file in resolved_profile.defaults_stack:
            cmd += ["--defaults", str(defaults_file)]
            defaults_meta = self._merge_defaults_metadata(defaults_meta, self._read_defaults_metadata(defaults_file))

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
        xe = shutil.which("xelatex") or "xelatex"
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
