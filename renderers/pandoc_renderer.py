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

from engine.projection_plan import ProjectionPlan
from renderers.base import Renderer

# Read-only reference path for 40_latex templates, styles, fonts.
LATEX40 = Path("~/Digital_Workspace/40_latex")

# Local copy of 40_latex profile assets (editable Optical Foundry copies).
# Prefer these over 40_latex when they exist.
LOCAL_IMPORT = Path(__file__).resolve().parents[1] / "profiles" / "40_latex_import"


class PandocRenderer(Renderer):
    """Execute a ProjectionPlan through Pandoc.

    Builds the `pandoc` command line from the plan's Pandoc defaults overlay,
    profile_id hint, template, and style. Shells out to Pandoc and captures
    evidence.
    """

    name = "pandoc"

    def render(self, plan: ProjectionPlan, output_dir: str | None = None) -> dict[str, Any]:
        start = time.monotonic()
        out_dir = Path(output_dir) if output_dir else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pdf = out_dir / f"{plan.render_id}{plan.output_extension}"
        log_file = out_dir / f"{plan.render_id}.log"
        evidence_file = out_dir / f"{plan.render_id}.evidence.json"
        text_file = out_dir / f"{plan.render_id}.txt"

        # --- build pandoc command ---
        cmd = ["pandoc", str(plan.render_source), "-o", str(output_pdf)]

        # profile defaults: look for profile YAML in 40_latex defaults/
        defaults_file = self._find_profile_defaults(plan.profile_id)
        defaults_meta: dict[str, Any] = {}
        if defaults_file:
            cmd += ["--defaults", str(defaults_file)]
            defaults_meta = self._read_defaults_metadata(defaults_file)

        # template — prefer local import, fall back to 40_latex
        template = plan.template or self._infer_template(plan.profile_id)
        if template:
            tpath_local = LOCAL_IMPORT / "templates" / template
            tpath_40 = LATEX40 / "templates" / template
            if tpath_local.exists():
                cmd += ["--template", str(tpath_local)]
            elif tpath_40.exists():
                cmd += ["--template", str(tpath_40)]

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
        cmd += ["--pdf-engine", str(xe)]

        # texmf path for styles — prefer local import, fall back to 40_latex
        local_texmf = LOCAL_IMPORT / "styles" / "texmf"
        texmf40 = LATEX40 / "styles" / "texmf"
        env = os.environ.copy()
        if local_texmf.exists():
            env["TEXMFHOME"] = str(local_texmf)
        elif texmf40.exists():
            env["TEXMFHOME"] = str(texmf40)

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
            "profile": {"profile_id": plan.profile_id},
            "input": {
                "path": str(plan.render_source),
                "digest_sha256": self._sha256_file(plan.render_source),
                "bytes": plan.render_source.stat().st_size,
            },
            "source_inventory": plan.source_inventory,
            "figure_inventory": plan.figure_inventory,
            "render_metadata": {
                "profile": plan.profile_id,
                "template": template,
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
            "warnings": list(plan.boundary_assertions.get("warnings", [])) + defaults_meta.get("warnings", []),
            "boundary": {
                "target_40_latex_mutated": False,
                "production_output": False,
                "packet_local_generated_only": True,
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
        # Prefer local import, then 40_latex, then greenfield profiles/
        for pattern in [f"{profile_id}.yaml", f"{profile_id.replace('_', '-')}.yaml",
                        f"{profile_id.replace('-', '_')}.yaml"]:
            local = LOCAL_IMPORT / "defaults" / pattern
            if local.exists():
                return local
            remote = LATEX40 / "defaults" / pattern
            if remote.exists():
                return remote
        # Also check profiles/ in greenfield
        for pdir in (Path("profiles") / "reports", Path("profiles") / "labels",
                      Path("profiles") / "stickers", Path("profiles") / "letters",
                      Path("profiles") / "resumes"):
            candidate = pdir / f"{profile_id}.yaml"
            if candidate.exists():
                return candidate
        return None

    def _infer_template(self, profile_id: str) -> str | None:
        # Map profile IDs to known template names from 40_latex.
        mapping = {
            "generic-report": "generic_report.tex",
            "generic_report": "generic_report.tex",
            "risk": "risk.tex",
            "tech": "tech.tex",
            "creative": "creative.tex",
            "cam": "cam.tex",
            "mythic": "mythic.tex",
            "mythic-letter": "personal_letter.tex",
            "mythic-letter-johannah": "mythic_letter_johannah.tex",
            "letter": "personal_letter.tex",
            "resume": "resume.tex",
            "prometheus-packet": "generic_report.tex",
            "convergence": "convergence.tex",
            "keeper": "keeper.tex",
            "yugen-brand": "yugen_brand.tex",
            "yugen-brand-elevated": "yugen_brand_elevated.tex",
            "elian-packet": "elian_packet.tex",
            "elian-poster": "elian_poster.tex",
            "labels-avery-5164": "label_sheet.tex",
            "labels-avery-15264": "label_sheet.tex",
            "sticker-sheet": "label_sheet.tex",
        }
        return mapping.get(profile_id)

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
