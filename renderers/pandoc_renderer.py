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
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from engine.codex_editions import (
    CodexEditionRenderError,
    edition_from_source_frontmatter,
    preprocess_codex_edition_blocks,
    source_contains_codex_edition_markers,
    source_contains_codex_editorial_callouts,
)
from engine.d2 import D2RenderError, preprocess_d2_blocks
from engine.graphviz import GraphvizRenderError, preprocess_graphviz_blocks
from engine.glyph_lint import format_missing_character_failures, scan_missing_character_warnings
from engine.furnish import (
    DividerMarkerSanitizationError,
    build_page_to_stock,
    compute_furnish,
    extract_divider_page_map,
    sanitize_divider_markers,
    write_divider_page_map,
    write_furnish_json,
    write_furnish_text,
)
from engine.imposition import ImpositionError, impose_pdf
from engine.bindery_preflight import generate_bindery_preflight
from engine.emoji_substitution import preprocess_emoji_substitutions
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
from engine.resource_roots import (
    ResolvedResourceRoot,
    effective_resource_roots,
    resource_resolution_evidence,
    resource_root_paths,
)
from renderers.base import Renderer


class FurnishMapError(RuntimeError):
    """Raised when preserved divider evidence cannot support a furnish map."""


class RenderArtifactPublicationError(RuntimeError):
    """Raised when validated render intermediates cannot be published safely."""


class PandocRenderer(Renderer):
    """Execute a ProjectionPlan through Pandoc.

    Builds the `pandoc` command line from the plan's Pandoc defaults overlay,
    profile_id hint, template, and style. Shells out to Pandoc and captures
    evidence.
    """

    name = "pandoc"

    def render(
        self,
        plan: ProjectionPlan,
        output_dir: str | None = None,
        *,
        measure: bool = False,
    ) -> dict[str, Any]:
        """Render ``plan`` to PDF and write evidence beside it.

        ``measure=True`` is for renders that exist only to be measured (page
        labels, extent) by a later pass: the PDF, text layer, glyph lint and
        divider handling are exactly as in a full render, but imposition and the
        bindery preflight (whose safe-area overlay typesets a second copy of the
        whole PDF) are skipped, and the evidence records ``render_mode:
        measure`` so the artifact cannot pass for a deliverable.
        """
        start = time.monotonic()
        out_dir = (Path(output_dir) if output_dir else Path.cwd()).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pdf = out_dir / f"{plan.render_id}{plan.output_extension}"
        log_file = out_dir / f"{plan.render_id}.log"
        evidence_file = out_dir / f"{plan.render_id}.evidence.json"
        text_file = out_dir / f"{plan.render_id}.txt"
        compile_token = uuid.uuid4().hex
        compile_pdf = out_dir / (
            f".{plan.render_id}.compile-stage-{compile_token}{plan.output_extension}"
        )
        compile_text_file = out_dir / (
            f".{plan.render_id}.compile-stage-{compile_token}.txt"
        )

        # --- build pandoc command ---
        try:
            resolved_profile = resolve_profile(plan.profile_id)
            plan = self._prepare_codex_edition_source(plan, out_dir, resolved_profile)
            plan = self._prepare_layout_image_source(plan, out_dir)
            plan = self._prepare_mermaid_source(plan, out_dir)
            plan = self._prepare_vega_source(plan, out_dir)
            plan = self._prepare_d2_source(plan, out_dir)
            plan = self._prepare_graphviz_source(plan, out_dir)
            plan = self._prepare_emoji_substitution_source(plan, out_dir)
        except (CodexEditionRenderError, LayoutImageRenderError, MermaidRenderError, VegaRenderError, D2RenderError, GraphvizRenderError) as exc:
            elapsed = time.monotonic() - start
            return self._evidence_error(
                plan, out_dir / f"{plan.render_id}{plan.output_extension}", evidence_file, elapsed, str(exc), ["source-preprocessor"]
            )

        render_source = plan.render_source.resolve()
        resource_roots = effective_resource_roots(plan, resolved_profile, out_dir)
        resource_resolution = resource_resolution_evidence(plan, resource_roots)

        # profile defaults/template/resource environment: single-object profile
        # resolution is centralized in engine.profile_resolver. Manifest-family
        # assembly decisions remain outside this renderer.
        cmd_source = self._stationery_normalized_source(
            render_source, out_dir, plan.render_id, resolved_profile.profile_family
        )
        cmd_source = self._titlepage_background_normalized_source(cmd_source, out_dir, plan.render_id)
        cmd = ["pandoc", str(cmd_source), "-o", str(compile_pdf)]
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
        font_runtime_defaults, font_runtime_fallbacks = self._font_runtime_defaults(
            resolved_profile.defaults_stack,
            out_dir,
            plan.render_id,
            page_geometry_defaults,
            source_header_includes=self._source_header_includes(cmd_source),
        )
        if font_runtime_defaults is not None:
            cmd += ["--defaults", str(font_runtime_defaults)]

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

        # Report-frontmatter contract: lower resolved classification, cover
        # metadata, footers, and PDF docinfo into pandoc -V/-M flags. These are
        # applied AFTER the profile --defaults so they override the profile's
        # division/confidentiality/footer_text defaults.
        cmd += self._document_settings_options(plan)

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

        cmd += self._resource_path_options(
            resource_roots,
            manifest_resource_roots=plan.manifest_resource_roots,
            legacy_profile_paths=resolved_profile.render_environment.resource_paths,
        )

        # Page geometry is lowered through a final defaults overlay so imported
        # templates that rely on `$geometry$` receive both the requested paper
        # size and their existing margin/profile geometry options.

        # --- execute ---
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._compile_timeout_s(),
                env=env,
                cwd=resolved_profile.render_environment.cwd,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            budget = self._compile_timeout_s()
            return self._evidence_error(
                plan,
                compile_pdf,
                evidence_file,
                elapsed,
                # Name the real stage. This subprocess is pandoc, but pandoc is
                # only the parent -- what actually burns the budget is the LaTeX
                # engine it drives, which pandoc reruns until cross-references
                # settle. "pandoc timed out" has sent at least one investigation
                # after the wrong process; say what to look at instead.
                f"PDF compile exceeded {budget}s (pandoc + {pdf_engine} reruns). "
                f"This is a BUDGET timeout, not necessarily a hang -- a heavy "
                f"volume can legitimately need several minutes. Check whether "
                f"{pdf_engine} was still making progress (ps/CPU, the .log tail) "
                f"before treating it as a defect; raise CODEX_COMPILE_TIMEOUT_S "
                f"if the render simply needs longer.",
                cmd,
            )

        elapsed = time.monotonic() - start
        success = result.returncode == 0 and compile_pdf.exists()

        # log
        render_log = result.stdout + "\n--- STDERR ---\n" + result.stderr
        log_file.write_text(render_log)

        if not success:
            return self._evidence_error(
                plan, compile_pdf, evidence_file, elapsed,
                f"pandoc exit {result.returncode}: {result.stderr[-500:]}", cmd
            )

        # --- extract compile-stage text for missing-glyph validation ---
        try:
            subprocess.run(
                ["pdftotext", str(compile_pdf), str(compile_text_file)],
                capture_output=True,
                timeout=60,
                check=True,
            )
            text_extract = compile_text_file.read_text(errors="replace")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            message = f"could not extract compile-stage PDF text layer: {exc}"
            return self._evidence_error(
                plan, compile_pdf, evidence_file, elapsed, message, cmd
            )

        # LuaLaTeX/Pandoc treats a missing font glyph as a warning and exits 0,
        # leaving .notdef tofu in the PDF. Promote that warning to a render
        # failure. The compile log gives the original codepoint; pdftotext's
        # form-feed-separated U+FFFD output supplies the physical PDF page.
        missing_characters = scan_missing_character_warnings(render_log, text_extract)
        if missing_characters:
            message = "missing-character lint failed: " + format_missing_character_failures(missing_characters)
            evidence = {
                "schema_version": "render_evidence_v1",
                "render_id": plan.render_id,
                "status": "error",
                "error": message,
                "validation": {
                    "status": "failed",
                    "checks": {
                        "pdf_written": False,
                        "text_extract_exists": bool(text_extract),
                        "all_sources_represented": len(plan.source_inventory) > 0,
                        "figure_inventory_recorded": isinstance(plan.figure_inventory, list),
                        "raw_latex_leakage": self._raw_latex_leakage(text_extract),
                        "missing_character_warnings": True,
                    },
                    "warning_count": len(missing_characters),
                    "errors": [message],
                },
                "output": {
                    "pdf_path": str(compile_pdf),
                    "pdf_pages": self._count_pages(compile_pdf),
                    "pdf_bytes": compile_pdf.stat().st_size,
                    "pdf_sha256": self._sha256_file(compile_pdf),
                    "publication_status": "withheld",
                },
                "missing_characters": missing_characters,
                "command": " ".join(cmd),
                "logs": str(log_file),
            }
            evidence_file.write_text(json.dumps(evidence, indent=2) + "\n")
            return evidence

        # --- preserve furnish map, then sanitize the intermediate PDF text ---
        divider_page_map: dict[str, int] = {}
        divider_marker_hygiene: dict[str, Any] = {
            "extracted_before_sanitization": 0,
            "removed_text_operations": 0,
            "final_pdf_marker_count": 0,
            "page_map_path": "",
        }
        publication_text_file = compile_text_file
        publication_extra_artifacts: tuple[tuple[Path, Path], ...] = ()
        divider_inventory = (plan.boundary_assertions or {}).get("section_dividers") or []
        # Marker coverage is driven by what the compile-stage PDF actually
        # CONTAINS, not by what the bundle declared. A source may carry a
        # hand-authored divider ritual in raw LaTeX (codex0 v5's encore
        # witnesses quad does) while the bundle's `section_dividers` list is
        # empty; gating extraction on the declared inventory left those markers
        # unsanitized in the reader-facing PDF and skipped the divider-page
        # sidecar entirely. The declared inventory remains an assertion on top:
        # every uid the bundle promised must still be found.
        divider_page_map = extract_divider_page_map(compile_pdf)
        if divider_inventory:
            expected_uids = {
                str(item.get("uid", "")).strip()
                for item in divider_inventory
                if str(item.get("uid", "")).strip()
            }
            missing_uids = sorted(expected_uids - set(divider_page_map))
            if missing_uids:
                message = "compile-stage OFDIV extraction missed divider uid(s): " + ", ".join(missing_uids)
                return self._evidence_error(
                    plan, compile_pdf, evidence_file, elapsed, message, cmd
                )
        if divider_page_map:
            page_map_path = out_dir / f"{plan.render_id}.divider_pages.json"
            page_map_stage_path = out_dir / (
                f".{plan.render_id}.divider-pages-stage-{compile_token}.json"
            )
            try:
                write_divider_page_map(
                    divider_page_map,
                    page_map_stage_path,
                    render_id=plan.render_id,
                )
                sanitization = sanitize_divider_markers(
                    compile_pdf, divider_page_map
                )
            except (DividerMarkerSanitizationError, OSError) as exc:
                return self._evidence_error(
                    plan, compile_pdf, evidence_file, elapsed, str(exc), cmd
                )

            # Extract into a second intermediate. The initial text remains useful
            # compile evidence until the sanitized PDF and refreshed text have
            # both passed verification and are ready for pair publication.
            publication_text_file = out_dir / (
                f".{plan.render_id}.sanitized-text-stage-{compile_token}.txt"
            )
            try:
                subprocess.run(
                    ["pdftotext", str(compile_pdf), str(publication_text_file)],
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                text_extract = publication_text_file.read_text(errors="replace")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                message = f"could not verify sanitized intermediate-PDF text layer: {exc}"
                return self._evidence_error(
                    plan, compile_pdf, evidence_file, elapsed, message, cmd
                )
            if "[[OFDIV:" in text_extract:
                message = "OFDIV marker survived sanitized text-sidecar refresh"
                return self._evidence_error(
                    plan, compile_pdf, evidence_file, elapsed, message, cmd
                )

            publication_extra_artifacts = ((page_map_stage_path, page_map_path),)
            divider_marker_hygiene = {
                "extracted_before_sanitization": len(divider_page_map),
                "removed_text_operations": sanitization.removed_text_operations,
                "pages_sanitized": sanitization.pages_sanitized,
                "final_pdf_marker_count": sanitization.final_pdf_marker_count,
                "page_map_path": str(page_map_path),
            }

        # Fail closed on any surviving marker, including the case where
        # extract_divider_page_map came back empty because its own pdftotext
        # subprocess failed (it returns {} rather than raising). Without this an
        # unsanitized `[[OFDIV:...]]` token could still reach a published PDF.
        if "[[OFDIV:" in text_extract:
            message = "OFDIV marker survived render finalization"
            return self._evidence_error(
                plan, compile_pdf, evidence_file, elapsed, message, cmd
            )

        warnings = (
            list(plan.boundary_assertions.get("warnings", []))
            + defaults_meta.get("warnings", [])
            + resolved_profile.warnings
            + resource_resolution["warnings"]
        )
        validation = self._validation_success(
            pdf_written=compile_pdf.exists(),
            text_extract=text_extract,
            source_inventory=plan.source_inventory,
            figure_inventory=plan.figure_inventory,
            warnings=warnings,
        )
        if validation["status"] != "passed":
            failed_checks = [
                name
                for name, value in validation["checks"].items()
                if (name in {"raw_latex_leakage", "missing_character_warnings"} and value)
                or (name not in {"raw_latex_leakage", "missing_character_warnings"} and not value)
            ]
            message = "render validation failed before publication"
            if failed_checks:
                message += ": " + ", ".join(failed_checks)
            validation["errors"] = [message]
            evidence = {
                "schema_version": "render_evidence_v1",
                "render_id": plan.render_id,
                "status": "error",
                "error": message,
                "validation": validation,
                "output": {
                    "pdf_path": str(compile_pdf),
                    "publication_status": "withheld",
                },
                "command": " ".join(cmd),
                "logs": str(log_file),
            }
            evidence_file.write_text(json.dumps(evidence, indent=2) + "\n")
            return evidence

        # Nothing final-named is touched until compile, glyph, marker, sanitizer,
        # and text-refresh checks have all passed. Publication uses atomic
        # same-directory replaces and bounded rollback of this artifact set.
        try:
            self._publish_render_artifacts(
                compile_pdf,
                publication_text_file,
                output_pdf,
                text_file,
                extra_artifacts=publication_extra_artifacts,
            )
        except RenderArtifactPublicationError as exc:
            return self._evidence_error(
                plan, compile_pdf, evidence_file, elapsed, str(exc), cmd
            )
        if publication_text_file != compile_text_file:
            try:
                compile_text_file.unlink(missing_ok=True)
            except OSError:
                pass

        # --- pdf info ---
        pdf_bytes = output_pdf.stat().st_size
        pdf_sha = self._sha256_file(output_pdf)
        pages = self._count_pages(output_pdf)
        if measure:
            imposition_output = None
            bindery_preflight = None
            # A preflight left by an earlier full render into this directory
            # describes a different PDF; do not let it sit beside this one.
            for stale in out_dir.glob(f"{plan.render_id}.safe_area_*"):
                stale.unlink(missing_ok=True)
            (out_dir / f"{plan.render_id}.bindery_preflight.json").unlink(missing_ok=True)
        else:
            imposition_output = self._maybe_impose_bound_pdf(
                plan,
                output_pdf,
                out_dir,
                divider_page_map=divider_page_map,
            )
            bindery_preflight = generate_bindery_preflight(
                output_pdf,
                out_dir=out_dir,
                plan=plan,
                imposition=imposition_output,
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
            "resource_resolution": resource_resolution,
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
                "font_runtime_defaults": str(font_runtime_defaults) if font_runtime_defaults else "",
                "font_runtime_fallbacks": font_runtime_fallbacks,
                "page_margin_options": plan.page_margins if page_geometry_options else [],
                "delivery": plan.delivery,
                "render_duration_ms": int(elapsed * 1000),
                "render_mode": "measure" if measure else "full",
                "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "success": success,
                "profile_version": defaults_meta.get("profile_version", "unknown"),
                **(plan.document_settings.evidence() if plan.document_settings else {}),
            },
            "output": {
                "pdf_path": str(output_pdf),
                "pdf_pages": pages,
                "pdf_bytes": pdf_bytes,
                "pdf_sha256": pdf_sha,
                "page_size": plan.page_size,
                **({"artifact_name": plan.document_settings.artifact_name} if plan.document_settings and plan.document_settings.artifact_name else {}),
                **({"imposition": imposition_output} if imposition_output else {}),
                **({"bindery_preflight": bindery_preflight} if bindery_preflight else {}),
            },
            "integrity": {
                "text_extract_exists": bool(text_extract),
                "expected_markers_found": [],
                "all_sources_represented": len(plan.source_inventory) > 0,
                "toc_present": plan.toc,
                "toc_depth": plan.toc_depth,
                "figures_validated": len(plan.figure_inventory) == 0,
                "divider_markers": divider_marker_hygiene,
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

    @staticmethod
    def _resource_path_options(
        roots: list[ResolvedResourceRoot],
        *,
        manifest_resource_roots: list[Path] | None = None,
        legacy_profile_paths: Iterable[Path] = (),
    ) -> list[str]:
        """Lower resource roots while preserving the absent-field runtime."""
        if manifest_resource_roots is not None and not manifest_resource_roots:
            options: list[str] = []
            for resource_path in legacy_profile_paths:
                if resource_path.exists():
                    options += ["--resource-path", str(resource_path)]
            return options
        if not roots:
            return []
        return ["--resource-path", os.pathsep.join(str(root.path) for root in roots)]

    @staticmethod
    def _document_settings_options(plan: ProjectionPlan) -> list[str]:
        """Lower resolved report settings into pandoc -V / -M flags.

        Native metadata (subject/keywords/lang) flows via -M so pandoc escapes
        it and populates $subject$/$keywords$/$lang$ (and PDF docinfo through the
        template's hypersetup). Presentation-only values flow via -V, which
        pandoc does NOT escape, so they are LaTeX-escaped here.
        """
        settings = plan.document_settings
        if settings is None:
            return []
        options: list[str] = []
        for key, value in settings.metadata().items():
            options += ["--metadata", f"{key}={value}"]
        for key, value in settings.template_variables().items():
            safe = value if key == "figure_numbering_section" else PandocRenderer._latex_header_text(value)
            options += ["--variable", f"{key}={safe}"]
        return options

    @staticmethod
    def _publish_render_artifacts(
        staged_pdf: Path,
        staged_text: Path,
        final_pdf: Path,
        final_text: Path,
        *,
        extra_artifacts: tuple[tuple[Path, Path], ...] = (),
    ) -> None:
        """Atomically replace validated render artifacts with bounded rollback.

        Every staged, final, and rollback path is in the same output directory,
        so each ``os.replace`` is a same-filesystem atomic operation. Since
        multiple directory entries cannot be replaced as one operation, prior
        finals are copied to private rollback paths first. If a later promotion
        fails, earlier promotions are restored (or removed when they had no
        predecessor). Rollback is deliberately bounded to this artifact set.
        """

        artifacts = (
            (staged_pdf, final_pdf),
            (staged_text, final_text),
            *extra_artifacts,
        )
        parents = {path.parent.resolve() for pair in artifacts for path in pair}
        if len(parents) != 1:
            raise RenderArtifactPublicationError(
                "render publication requires staged and final artifacts in one directory"
            )
        missing = [str(staged) for staged, _final in artifacts if not staged.is_file()]
        if missing:
            raise RenderArtifactPublicationError(
                "validated render intermediate missing before publication: "
                + ", ".join(missing)
            )

        rollback_paths: dict[Path, Path | None] = {}
        try:
            for _staged, final in artifacts:
                if final.exists():
                    rollback = final.with_name(
                        f".{final.name}.rollback-{uuid.uuid4().hex}"
                    )
                    shutil.copy2(final, rollback)
                    rollback_paths[final] = rollback
                else:
                    rollback_paths[final] = None
        except OSError as exc:
            for rollback in rollback_paths.values():
                if rollback is not None:
                    try:
                        rollback.unlink(missing_ok=True)
                    except OSError:
                        pass
            raise RenderArtifactPublicationError(
                f"could not prepare render publication rollback: {exc}"
            ) from exc

        promoted: list[Path] = []
        try:
            for staged, final in artifacts:
                os.replace(staged, final)
                promoted.append(final)
        except OSError as exc:
            rollback_errors: list[str] = []
            for final in reversed(promoted):
                rollback = rollback_paths[final]
                try:
                    if rollback is None:
                        final.unlink(missing_ok=True)
                    else:
                        os.replace(rollback, final)
                except OSError as rollback_exc:
                    rollback_errors.append(f"{final}: {rollback_exc}")
            detail = f"could not publish validated render artifacts: {exc}"
            if rollback_errors:
                detail += "; bounded rollback failed for " + "; ".join(rollback_errors)
            raise RenderArtifactPublicationError(detail) from exc
        finally:
            for rollback in rollback_paths.values():
                if rollback is not None:
                    try:
                        rollback.unlink(missing_ok=True)
                    except OSError:
                        pass

    def _maybe_impose_bound_pdf(
        self,
        plan: ProjectionPlan,
        output_pdf: Path,
        out_dir: Path,
        *,
        divider_page_map: dict[str, int] | None = None,
    ) -> dict[str, Any] | None:
        imposition = plan.delivery.get("imposition", {}) if isinstance(plan.delivery.get("imposition", {}), dict) else {}
        if plan.delivery.get("mode") != "bound" or not imposition.get("enabled"):
            return None
        try:
            result = impose_pdf(
                output_pdf,
                output=out_dir / "imposition",
                page_size=plan.page_size,
                sheet_size=str(imposition.get("sheet_size", "letter")),
                signature_size=int(imposition.get("signature_size", 4)),
                duplex_mode=str(imposition.get("duplex", "short_edge")),
            )
        except ImpositionError as exc:
            return {
                "status": "error",
                "error": str(exc),
                "layout": str(imposition.get("layout", "booklet_signature_2up")),
            }
        try:
            furnish_summary = self._emit_furnish_map(
                plan,
                output_pdf,
                Path(result.mapping_json),
                divider_page_map=divider_page_map,
            )
        except FurnishMapError as exc:
            return {
                "status": "error",
                "stage": "furnish",
                "error": str(exc),
                "layout": str(imposition.get("layout", "booklet_signature_2up")),
                "input_pdf": str(output_pdf),
                "output_pdf": str(result.output_pdf),
                "mapping_json": str(result.mapping_json),
            }
        payload: dict[str, Any] = {
            "status": "ok",
            "layout": str(imposition.get("layout", "booklet_signature_2up")),
            "input_pdf": str(output_pdf),
            "output_pdf": str(result.output_pdf),
            "mapping_json": str(result.mapping_json),
            "page_size": plan.page_size,
            "sheet_size": str(imposition.get("sheet_size", "letter")),
            "signature_size": int(imposition.get("signature_size", 4)),
            "duplex": str(imposition.get("duplex", "short_edge")),
            "input_pages": result.input_pages,
            "output_pages": result.output_pages,
            "padded_pages": result.padded_pages,
            "blank_count": result.blank_count,
        }
        if furnish_summary is not None:
            payload["furnish"] = furnish_summary
        return payload

    def _emit_furnish_map(
        self,
        plan: ProjectionPlan,
        output_pdf: Path,
        imposition_mapping_path: Path,
        *,
        divider_page_map: dict[str, int] | None = None,
    ) -> dict[str, Any] | None:
        """Compute + write .furnish.json + .furnish.txt next to the imposition mapping.

        Consumes the divider-page map extracted from the compile-stage PDF before
        final-PDF sanitization, joins it to the divider inventory in
        boundary_assertions, walks the imposition mapping, and emits the furnish
        sidecars. The sanitized reader-facing PDF intentionally contains no
        `[[OFDIV:<uid>]]` tokens and is never used as an extraction fallback.
        Returns a small summary for render evidence; returns None if there is no
        divider inventory or the imposition mapping is unreadable. Raises
        :class:`FurnishMapError` when divider inventory exists without the
        preserved map needed to furnish it safely.
        """
        boundary = plan.boundary_assertions or {}
        divider_inventory = boundary.get("section_dividers") or []
        if not divider_inventory:
            return None
        if not divider_page_map:
            raise FurnishMapError(
                "furnish requires the preserved pre-sanitization divider-page map"
            )

        page_map = dict(divider_page_map)
        expected_uids = {
            str(item.get("uid", "")).strip()
            for item in divider_inventory
            if str(item.get("uid", "")).strip()
        }
        missing_uids = sorted(expected_uids - set(page_map))
        if missing_uids:
            raise FurnishMapError(
                "preserved divider-page map is incomplete for furnish: "
                + ", ".join(missing_uids)
            )

        try:
            mapping = json.loads(imposition_mapping_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        total_pages = int(mapping.get("padded_pages", 0) or 0)
        page_to_stock = build_page_to_stock(total_pages, page_map, divider_inventory)
        furnish = compute_furnish(
            mapping,
            page_to_stock,
            input_pdf=output_pdf,
            imposition_mapping_path=imposition_mapping_path,
            divider_page_map=page_map,
        )
        furnish_json = imposition_mapping_path.with_suffix(".furnish.json")
        furnish_txt = imposition_mapping_path.with_suffix(".furnish.txt")
        write_furnish_json(furnish, furnish_json)
        write_furnish_text(furnish, furnish_txt)
        return {
            "furnish_json": str(furnish_json),
            "furnish_txt": str(furnish_txt),
            "divider_page_map_count": len(page_map),
            "stock_summary": dict(furnish.stock_summary),
            "warning_count": len(furnish.warnings),
        }

    def _prepare_codex_edition_source(
        self,
        plan: ProjectionPlan,
        out_dir: Path,
        resolved_profile: ResolvedProfile,
    ) -> ProjectionPlan:
        """Select source-visible Codex 0 edition variants before other preprocessors.

        The culler is intentionally fail-closed: if `cx0:` edition sentinels are
        present under a non-Codex profile, rendering fails rather than leaking all
        editions into a reader proof. Sources without sentinels are unchanged.
        """

        if not plan.render_source.exists():
            return plan

        has_markers = source_contains_codex_edition_markers(plan.render_source)
        has_callouts = source_contains_codex_editorial_callouts(plan.render_source)
        edition, strip_callouts = edition_from_source_frontmatter(plan.render_source)
        has_codex_controls = has_markers or bool(edition) or strip_callouts
        if has_codex_controls and resolved_profile.canonical_profile_id != "codex0":
            raise CodexEditionRenderError(
                f"Codex edition controls require profile codex0; got {resolved_profile.canonical_profile_id}"
            )

        if resolved_profile.canonical_profile_id != "codex0":
            return plan

        format_callouts = has_callouts and not strip_callouts
        if not has_markers and not strip_callouts and not format_callouts:
            return plan

        result = preprocess_codex_edition_blocks(
            plan.render_source,
            out_dir,
            plan.render_id,
            edition,
            strip_editorial_callouts=strip_callouts,
            format_editorial_callouts=format_callouts,
        )
        if not result.changed:
            return plan

        boundary = dict(plan.boundary_assertions)
        warnings = [*boundary.get("warnings", []), *result.warnings]
        boundary.update(
            {
                "codex_edition_preprocessor_enabled": True,
                "codex_edition_profile_scope": resolved_profile.canonical_profile_id,
                "codex_edition": result.edition,
                "codex_edition_variant_count": result.variant_count,
                "codex_edition_selected_count": result.selected_count,
                "codex_edition_fallback_count": result.fallback_count,
                "codex_edition_selected_variant_ids": result.selected_variant_ids,
                "codex_edition_fallback_variant_ids": result.fallback_variant_ids,
                "codex_editorial_callouts_stripped": result.editorial_callouts_stripped,
                "codex_editorial_callouts_formatted": result.editorial_callouts_formatted,
                "codex_edition_render_mode": "pre_pandoc_comment_sentinel_culler",
            }
        )
        if warnings:
            boundary["warnings"] = warnings
        return replace(plan, render_source=result.rewritten_source, boundary_assertions=boundary)

    def _prepare_emoji_substitution_source(
        self,
        plan: ProjectionPlan,
        out_dir: Path,
    ) -> ProjectionPlan:
        """Rewrite supported emoji to vendored image assets for PDF/LaTeX output."""

        if not plan.render_source.exists():
            return plan

        resolved_profile = resolve_profile(plan.profile_id)
        if not self._layout_images_supported(plan, resolved_profile):
            return plan

        result = preprocess_emoji_substitutions(plan.render_source, out_dir, plan.render_id)
        if not result.changed:
            return plan

        boundary = dict(plan.boundary_assertions)
        figure_count_by_kind = dict(boundary.get("figure_count_by_kind", {}))
        total = 0
        counts_by_key: dict[str, int] = {}
        for entry in result.inventory:
            kind = str(entry.get("kind", "emoji_asset"))
            count = int(entry.get("count", 0))
            figure_count_by_kind[kind] = figure_count_by_kind.get(kind, 0) + count
            total += count
            counts_by_key[str(entry.get("asset_key", ""))] = count

        warnings = [*boundary.get("warnings", []), *result.warnings]
        boundary.update(
            {
                "emoji_policy": "vendored_image_assets",
                "emoji_asset_family": "noto_emoji",
                "emoji_render_mode": "pre_pandoc_raw_latex_inline_image",
                "emoji_substitution_count": total,
                "emoji_substitution_counts_by_key": counts_by_key,
                "emoji_asset_paths": result.asset_paths,
                "host_emoji_fonts_required": False,
                "figure_count_by_kind": figure_count_by_kind,
            }
        )
        if warnings:
            boundary["warnings"] = warnings

        return replace(
            plan,
            render_source=result.rewritten_source,
            figure_inventory=[*plan.figure_inventory, *result.inventory],
            boundary_assertions=boundary,
        )

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

        if plan.manifest_resource_roots:
            roots = effective_resource_roots(plan, resolved_profile, out_dir)
            layout_roots = resource_root_paths(roots)
        else:
            # Preserve the clean-HEAD layout search order when the additive
            # manifest field is absent: authored source, render output, then the
            # profile/source compatibility roots used by the prior runtime.
            layout_roots = [
                plan.render_source.resolve().parent,
                Path(out_dir).resolve(),
                LOCAL_IMPORT,
                *resolved_profile.asset_roots,
                *plan.source_resource_roots,
            ]
        result = preprocess_layout_image_blocks(
            plan.render_source,
            out_dir,
            plan.render_id,
            layout_roots,
            force_graphicspath=bool(plan.manifest_resource_roots),
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

        settings = plan.document_settings
        result = preprocess_vega_blocks(
            plan.render_source,
            profile_id=plan.profile_id,
            output_dir=out_dir,
            render_id=plan.render_id,
            renderer=vega_renderer,
            output_format=vega_output_format,
            figure_captions=bool(settings.figure_captions) if settings else False,
            figure_numbering=bool(settings.figure_numbering) if settings else False,
            figure_numbering_section=bool(settings.figure_numbering_section) if settings else False,
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
        profile_version = right.get("profile_version") or left.get("profile_version")
        if profile_version:
            merged["profile_version"] = profile_version
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
    def _font_runtime_defaults(
        defaults_stack: list[Path],
        out_dir: Path,
        render_id: str,
        base_defaults: Path | None = None,
        source_header_includes: list[str] | None = None,
    ) -> tuple[Path | None, list[dict[str, str]]]:
        """Materialize a render-only font fallback overlay for non-macOS hosts.

        Several imported profile defaults name macOS fonts such as Helvetica or
        Menlo. The profile resolver records those names as declared system
        fallbacks, but XeTeX/fontspec still needs an actual installed family at
        render time. On Sol/Linux, use installed Noto families through a final
        Pandoc defaults overlay instead of mutating the canonical profile tree.
        """
        requested = PandocRenderer._collect_font_variables(defaults_stack)
        if not requested:
            return None, []
        available = PandocRenderer._available_font_families()
        fallback_map = {
            "Helvetica": "DejaVu Sans",
            "Avenir Next": "DejaVu Sans",
            "Dune Rise": "DejaVu Sans",
            "Menlo": "DejaVu Sans Mono",
            "Iowan Old Style": "DejaVu Serif",
            "Times New Roman": "DejaVu Serif",
            "Apple Color Emoji": "Noto Color Emoji",
        }
        variables: dict[str, str] = {}
        fallbacks: list[dict[str, str]] = []
        for role, family in requested.items():
            if family in available:
                continue
            fallback = fallback_map.get(family)
            if fallback and PandocRenderer._font_fallback_allowed(fallback, available):
                variables[role] = fallback
                fallbacks.append({"role": role, "requested": family, "applied": fallback})

        header_includes = [*(source_header_includes or []), *PandocRenderer._header_includes_from_defaults(base_defaults)]
        yugen_font_roles = {
            "mainfont": "Times New Roman",
            "sansfont": "Helvetica",
            "monofont": "Menlo",
        }
        yugen_font_values = {
            role: fallback_map.get(family, family)
            for role, family in yugen_font_roles.items()
            if family not in available and PandocRenderer._font_fallback_allowed(fallback_map.get(family, ""), available)
        }
        if yugen_font_values:
            mainfont = yugen_font_values.get("mainfont", "DejaVu Serif")
            sansfont = yugen_font_values.get("sansfont", "DejaVu Sans")
            monofont = yugen_font_values.get("monofont", "DejaVu Sans Mono")
            header_includes.append(
                "\\makeatletter\n"
                "\\@ifundefined{yugen@setfonts}{}{\\renewcommand\\yugen@setfonts{%\n"
                f"  \\setmainfont{{{mainfont}}}%\n"
                f"  \\setsansfont{{{sansfont}}}[Scale=MatchLowercase]%\n"
                f"  \\setmonofont{{{monofont}}}[Scale=MatchLowercase]%\n"
                "}}\n"
                "\\makeatother"
            )
            for role, family in yugen_font_roles.items():
                applied = yugen_font_values.get(role)
                if applied:
                    fallbacks.append({"role": f"yugencommon.{role}", "requested": family, "applied": applied})

        if not variables and not header_includes:
            return None, []
        path = out_dir / f"{render_id}.font_fallbacks.yaml"
        import yaml
        payload: dict[str, Any] = {}
        if variables:
            payload["variables"] = variables
        if header_includes:
            payload.setdefault("variables", {})["header-includes"] = list(dict.fromkeys(header_includes))
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
        return path, fallbacks

    @staticmethod
    def _collect_font_variables(defaults_stack: list[Path]) -> dict[str, str]:
        merged: dict[str, str] = {}
        file_backed_roles: set[str] = set()
        try:
            import yaml
        except Exception:
            return merged
        for defaults_file in defaults_stack:
            try:
                data = yaml.safe_load(defaults_file.read_text()) or {}
            except Exception:
                continue
            variables = data.get("variables", {}) if isinstance(data, dict) else {}
            if not isinstance(variables, dict):
                continue
            for role in ("mainfont", "sansfont", "monofont"):
                if variables.get(f"{role}_file"):
                    file_backed_roles.add(role)
                    merged.pop(role, None)
                    continue
                value = variables.get(role)
                if role not in file_backed_roles and isinstance(value, str) and value.strip():
                    merged[role] = value.strip()
        return merged

    @staticmethod
    def _font_fallback_allowed(family: str, available: set[str]) -> bool:
        if not family:
            return False
        # DejaVu families are part of the baseline NixOS/XeTeX surface even
        # when fontconfig reports only the primary Sans family in `fc-list`.
        return family in available or family.startswith("DejaVu ")

    @staticmethod
    def _header_includes_from_defaults(defaults_path: Path | None) -> list[str]:
        if defaults_path is None or not defaults_path.exists():
            return []
        try:
            import yaml
            data = yaml.safe_load(defaults_path.read_text()) or {}
        except Exception:
            return []
        variables = data.get("variables", {}) if isinstance(data, dict) else {}
        header_includes = variables.get("header-includes", []) if isinstance(variables, dict) else []
        if isinstance(header_includes, str):
            return [header_includes]
        if isinstance(header_includes, list):
            return [str(item) for item in header_includes]
        return []

    @staticmethod
    def _available_font_families() -> set[str]:
        try:
            result = subprocess.run(
                ["fc-list", ":", "family"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return set()
        families: set[str] = set()
        for line in result.stdout.splitlines():
            for family in line.split(","):
                family = family.strip()
                if family:
                    families.add(family)
        return families

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
        if isinstance(vars_, dict) and vars_.get("profile_version"):
            out["profile_version"] = str(vars_["profile_version"])
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
            illumination = plan.delivery.get("illumination", {}) if isinstance(plan.delivery.get("illumination", {}), dict) else {}
            if illumination.get("enabled"):
                variables["of_illumination_rail_width"] = str(illumination.get("width", "0.45in"))
                variables["of_illumination_bottom_height"] = str(illumination.get("bottom_height", "0.30in"))
                variables["of_illumination_bottom_offset"] = str(illumination.get("bottom_offset", "0.28in"))
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
        illumination = plan.delivery.get("illumination", {}) if isinstance(plan.delivery.get("illumination", {}), dict) else {}
        if illumination.get("enabled"):
            includes.append(
                PandocRenderer._bound_illumination_rail_header_include(
                    str(illumination.get("width", "0.45in")),
                    bottom_enabled=bool(illumination.get("bottom")) or "bottom" in (illumination.get("rails") if isinstance(illumination.get("rails"), list) else [illumination.get("rail", "outer")]),
                    bottom_height=str(illumination.get("bottom_height", "0.30in")),
                    bottom_offset=str(illumination.get("bottom_offset", "0.28in")),
                    inner_margin=str(plan.delivery.get("margins", {}).get("inner", "0.85in")) if isinstance(plan.delivery.get("margins", {}), dict) else "0.85in",
                    outer_margin=str(plan.delivery.get("margins", {}).get("outer", "0.60in")) if isinstance(plan.delivery.get("margins", {}), dict) else "0.60in",
                    top_margin=str(plan.delivery.get("margins", {}).get("top", "0.65in")) if isinstance(plan.delivery.get("margins", {}), dict) else "0.65in",
                )
            )
        return includes

    @staticmethod
    def _bound_illumination_rail_header_include(
        width: str,
        *,
        bottom_enabled: bool = False,
        bottom_height: str = "0.30in",
        bottom_offset: str = "0.28in",
        inner_margin: str = "0.85in",
        outer_margin: str = "0.60in",
        top_margin: str = "0.65in",
        critical_safe_inset: str = "0.25in",
    ) -> str:
        bottom = ""
        if bottom_enabled:
            bottom = (
                "\n\\newlength{\\OFIlluminationBottomRailWidth}\n"
                "\\newlength{\\OFIlluminationBottomRailHeight}\n"
                "\\newlength{\\OFIlluminationBottomOffset}\n"
                "\\setlength{\\OFIlluminationBottomRailWidth}{\\textwidth}\n"
                f"\\setlength{{\\OFIlluminationBottomRailHeight}}{{{bottom_height}}}\n"
                f"\\setlength{{\\OFIlluminationBottomOffset}}{{{bottom_offset}}}\n"
                "\\newcommand{\\OFBottomRail}[1]{%\n"
                "  \\begin{tikzpicture}[remember picture,overlay]\n"
                "    \\ifodd\\value{page}%\n"
                "      \\node[anchor=south west,inner sep=0pt,xshift=\\OFBoundInnerMargin,yshift=\\OFIlluminationBottomOffset] at (current page.south west) {\\includegraphics[width=\\OFIlluminationBottomRailHeight,height=\\OFIlluminationBottomRailWidth,angle=90]{\\detokenize{#1}}};%\n"
                "    \\else%\n"
                "      \\node[anchor=south west,inner sep=0pt,xshift=\\OFBoundOuterMargin,yshift=\\OFIlluminationBottomOffset] at (current page.south west) {\\includegraphics[width=\\OFIlluminationBottomRailHeight,height=\\OFIlluminationBottomRailWidth,angle=90]{\\detokenize{#1}}};%\n"
                "    \\fi%\n"
                "  \\end{tikzpicture}%\n"
                "}"
            )
        return (
            "\\usepackage{graphicx}\n"
            "\\usepackage{tikz}\n"
            "\\usepackage{wrapfig}\n"
            "\\newlength{\\OFIlluminationRailWidth}\n"
            "\\newlength{\\OFIlluminationRailSep}\n"
            "\\newlength{\\OFBoundInnerMargin}\n"
            "\\newlength{\\OFBoundOuterMargin}\n"
            "\\newlength{\\OFBoundTopMargin}\n"
            "\\newlength{\\OFBinderyCriticalSafeInset}\n"
            f"\\setlength{{\\OFIlluminationRailWidth}}{{{width}}}\n"
            "\\setlength{\\OFIlluminationRailSep}{0.05in}\n"
            f"\\setlength{{\\OFBoundInnerMargin}}{{{inner_margin}}}\n"
            f"\\setlength{{\\OFBoundOuterMargin}}{{{outer_margin}}}\n"
            f"\\setlength{{\\OFBoundTopMargin}}{{{top_margin}}}\n"
            f"\\setlength{{\\OFBinderyCriticalSafeInset}}{{{critical_safe_inset}}}\n"
            "\\setlength{\\marginparwidth}{\\OFIlluminationRailWidth}\n"
            "\\setlength{\\marginparsep}{\\OFIlluminationRailSep}\n"
            "\\makeatletter\n"
            "\\newcommand{\\OFEO@edge}{outer}\n"
            "\\newcommand{\\OFEO@anchor}{top}\n"
            "\\newcommand{\\OFEO@mirror}{none}\n"
            "\\newcommand{\\OFEO@width}{\\OFIlluminationRailWidth}\n"
            "\\newcommand{\\OFEO@yoffset}{0pt}\n"
            "\\newcommand{\\OFEO@xoffset}{0pt}\n"
            "\\newcommand{\\OFEO@wrap}{false}\n"
            "\\pgfkeys{/ofedgeornament/.is family,/ofedgeornament,edge/.store in=\\OFEO@edge,anchor/.store in=\\OFEO@anchor,mirror/.store in=\\OFEO@mirror,width/.store in=\\OFEO@width,yoffset/.store in=\\OFEO@yoffset,xoffset/.store in=\\OFEO@xoffset,wrap/.store in=\\OFEO@wrap}\n"
            "\\newcommand{\\OFEO@includegraphics}[1]{\\includegraphics[width=\\OFEO@width]{\\detokenize{#1}}}\n"
            "\\newcommand{\\OFEO@safeOuterRectoXShift}{\\dimexpr-\\OFBinderyCriticalSafeInset-\\OFEO@xoffset\\relax}\n"
            "\\newcommand{\\OFEO@safeOuterVersoXShift}{\\dimexpr\\OFBinderyCriticalSafeInset+\\OFEO@xoffset\\relax}\n"
            "\\newcommand{\\OFEO@topYShift}{\\dimexpr-\\OFBoundTopMargin-\\OFEO@yoffset\\relax}\n"
            "\\newcommand{\\OFEO@maybeReflect}[1]{%\n"
            "  \\def\\OFEO@mirrorInward{inward}%\n"
            "  \\ifx\\OFEO@mirror\\OFEO@mirrorInward\\ifodd\\value{page}#1\\else\\reflectbox{#1}\\fi\\else#1\\fi%\n"
            "}\n"
            "\\newcommand{\\OFEO@placePage}[1]{%\n"
            "  \\begin{tikzpicture}[remember picture,overlay]%\n"
            "    \\ifodd\\value{page}%\n"
            "      \\node[anchor=north east,inner sep=0pt,xshift=\\OFEO@safeOuterRectoXShift,yshift=\\OFEO@topYShift] at (current page.north east) {\\OFEO@maybeReflect{\\OFEO@includegraphics{#1}}};%\n"
            "    \\else%\n"
            "      \\node[anchor=north west,inner sep=0pt,xshift=\\OFEO@safeOuterVersoXShift,yshift=\\OFEO@topYShift] at (current page.north west) {\\OFEO@maybeReflect{\\OFEO@includegraphics{#1}}};%\n"
            "    \\fi%\n"
            "  \\end{tikzpicture}%\n"
            "}\n"
            "\\newcommand{\\OFEO@placeParagraphRail}[1]{\\marginpar{\\centering\\OFEO@maybeReflect{\\OFEO@includegraphics{#1}}}}\n"
            "\\newcommand{\\OFEO@placeParagraphWrap}[1]{%\n"
            "  \\begin{wrapfigure}{o}{\\dimexpr\\OFEO@width+0.08in\\relax}%\n"
            "    \\vspace{-0.8\\baselineskip}\\centering\\OFEO@maybeReflect{\\OFEO@includegraphics{#1}}\\vspace{-0.4\\baselineskip}%\n"
            "  \\end{wrapfigure}%\n"
            "}\n"
            "\\newcommand{\\OFEO@placeParagraph}[1]{%\n"
            "  \\def\\OFEO@wrapTrue{true}\\def\\OFEO@wrapAuto{auto}\\def\\OFEO@wrapNow{false}%\n"
            "  \\ifx\\OFEO@wrap\\OFEO@wrapTrue\\def\\OFEO@wrapNow{true}\\fi%\n"
            "  \\ifx\\OFEO@wrap\\OFEO@wrapAuto\\ifdim\\OFEO@width>\\OFIlluminationRailWidth\\def\\OFEO@wrapNow{true}\\fi\\fi%\n"
            "  \\ifx\\OFEO@wrapNow\\OFEO@wrapTrue\\OFEO@placeParagraphWrap{#1}\\else\\OFEO@placeParagraphRail{#1}\\fi%\n"
            "}\n"
            "\\newcommand{\\OFEdgeOrnament}[2][]{%\n"
            "  \\begingroup%\n"
            "  \\pgfkeys{/ofedgeornament,edge=outer,anchor=top,mirror=none,width=\\OFIlluminationRailWidth,yoffset=0pt,xoffset=0pt,wrap=false,#1}%\n"
            "  \\def\\OFEO@anchorParagraph{paragraph}%\n"
            "  \\ifx\\OFEO@anchor\\OFEO@anchorParagraph\\OFEO@placeParagraph{#2}\\else\\OFEO@placePage{#2}\\fi%\n"
            "  \\endgroup%\n"
            "}\n"
            "\\makeatother\n"
            "\\newcommand{\\OFOuterRail}[1]{%\n"
            "  \\marginpar{\\centering\\includegraphics[width=\\OFIlluminationRailWidth]{\\detokenize{#1}}}%\n"
            "}"
            f"{bottom}"
        )

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
        safe_variable_candidates: dict[str, Any] = {}
        if isinstance(variables, dict):
            safe_variable_candidates.update(variables)

        # Imported 40_latex letter profiles historically treated simple source
        # frontmatter fields such as `artifact_series` and `penned_date` as
        # template variables. Preserve that source-local override path without
        # requiring artifact remaster files to mutate shared profile defaults.
        direct_variable_keys = {
            "accent_color",
            "artifact_footer",
            "artifact_header",
            "artifact_location",
            "artifact_mark",
            "artifact_series",
            "body_color",
            "body_top_vspace",
            "bottom_right_art",
            "bottom_right_mask",
            "closing",
            "conceived_date",
            "desk_of",
            "header_art",
            "header_art_overlay",
            "header_art_reserved_vspace",
            "header_art_width",
            "header_art_xshift",
            "header_art_yshift",
            "linestretch",
            "opening",
            "ornament_color",
            "parindent",
            "parskip",
            "penned_date",
            "render_title",
            "rule_color",
            "signature_name",
            "stationery_footer_icon",
            "stationery_grid",
            "stationery_grid_icon",
            "stationery_grid_opacity",
            "stationery_grid_size",
            "stationery_grid_step",
            "stationery_header_center",
            "stationery_mode",
            "top_left_art",
            "top_right_mask",
        }
        for key in direct_variable_keys:
            if key in frontmatter:
                safe_variable_candidates[key] = frontmatter[key]
        variables = safe_variable_candidates
        if not variables:
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
            "missing_character_warnings": False,
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
                "missing_character_warnings": False,
            },
            "warning_count": 0,
            "errors": [message],
        }

    # PDF compile budget. Was a bare `timeout=300` literal with no stated basis.
    #
    # Canto 0 Vol II is a ~380 MB, 200+ page volume carrying full-resolution
    # witness plates, and pandoc reruns the LaTeX engine until cross-references
    # settle -- so the real cost is (engine passes x per-pass seconds), and a
    # single pass on that volume is already ~100s. It had been sitting inside
    # ~10% of the old 300s ceiling, which meant ANY legitimate addition read as
    # an infrastructure failure: restoring the 421 ruled whisper ornaments on
    # 2026-08-06 cost ~13% render time and tipped it over, and the resulting
    # "pandoc timed out" was investigated as a hang for hours. It was never a
    # hang -- every render involved completes, just slowly.
    #
    # 1800s is deliberately generous: this is a backstop against a genuinely
    # wedged process, NOT a performance budget. A real infinite loop still gets
    # caught; a heavy book no longer gets misreported as one. Override with
    # CODEX_COMPILE_TIMEOUT_S.
    DEFAULT_COMPILE_TIMEOUT_S = 1800

    @classmethod
    def _compile_timeout_s(cls) -> int:
        raw = os.environ.get("CODEX_COMPILE_TIMEOUT_S")
        if raw:
            try:
                value = int(raw)
                if value > 0:
                    return value
            except ValueError:
                pass
        return cls.DEFAULT_COMPILE_TIMEOUT_S

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
