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
from pathlib import Path
from typing import Any, Iterable

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
from engine.image_bake import (
    ACCEPTED_DEVIATION as IMAGE_BAKE_ACCEPTED_DEVIATION,
    bake_paths as bake_image_paths,
    cache_dir as image_bake_cache_dir,
    discover_png_references,
    lua_callback_source as image_bake_lua,
)
from engine.page_size import (
    collect_profile_classoption,
    collect_profile_geometry,
    merge_page_size_classoption,
    merge_page_size_geometry,
    normalize_page_size,
)
from engine.profile_resolver import LOCAL_IMPORT, ResolvedProfile, resolve_profile
from engine.projection_plan import ProjectionPlan
from engine.preamble import Preamble, source_header_includes
from engine.template_contract import contract_text
from engine.ornaments import OrnamentError, filter_metadata as ornament_filter_metadata, plan_ornaments
from engine.source_preparation import (
    PREPARATION_ERRORS,
    prepare as prepare_source,
    safe_frontmatter_resource_path,
)
from engine.resource_roots import (
    ResolvedResourceRoot,
)
from renderers.base import Renderer


class FurnishMapError(RuntimeError):
    """Raised when preserved divider evidence cannot support a furnish map."""


class RenderArtifactPublicationError(RuntimeError):
    """Raised when validated render intermediates cannot be published safely."""


# pandoc 3's stock LaTeX template block for `strikeout`, guarded so a template
# that already defines \st keeps its own.
STRIKEOUT_HEADER = (
    "% Optical Foundry strikeout support (pandoc lowers ~~text~~ to \\st).\n"
    "\\ifdefined\\st\\else\n"
    "\\ifdefined\\directlua\\usepackage{luacolor}\\usepackage[soul]{lua-ul}\n"
    "\\else\\usepackage{soul}\\fi\n"
    "\\fi\n"
)


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
        draft: bool = False,
        bake_images: bool = False,
    ) -> dict[str, Any]:
        """Render ``plan`` to PDF and write evidence beside it.

        ``measure=True`` is for renders that exist only to be measured (page
        labels, extent) by a later pass: the PDF, text layer, glyph lint and
        divider handling are exactly as in a full render, but imposition and the
        bindery preflight (whose safe-area overlay typesets a second copy of the
        whole PDF) are skipped, and the evidence records ``render_mode:
        measure`` so the artifact cannot pass for a deliverable.

        ``draft=True`` implies ``measure`` and also sets graphicx to draft
        (``\\setkeys{Gin}{draft=true}``): every image keeps its box but no image
        data is read, decoded or embedded. Pagination, page labels, text and
        outline destinations are unchanged (proved on all three Codex 0 volumes,
        2026-09-28), at a fifth to a twentieth of the compile time. Evidence
        records ``render_mode: draft``; prove a final against its draft with
        ``engine.pass_gates.compare_renders``.

        ``bake_images=True`` turns on the lossless image bake
        (``engine.image_bake``): a LuaTeX ``find_image_file`` callback redirects
        each alpha PNG already in the bake cache to its pre-split PDF, which
        LuaTeX embeds by copy instead of decoding and recompressing the PNG on
        every run. The PNGs this render names are baked before the compile, so
        the first render benefits too. The embedded image data is the same either
        way. LuaLaTeX only; evidence records what was referenced and baked under
        ``render_metadata.image_bake``.
        """
        if draft:
            measure = True
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

        # --- source preparation: every rewrite before pandoc (engine/source_preparation.py) ---
        resolved_profile = resolve_profile(plan.profile_id)
        try:
            prepared = prepare_source(plan, resolved_profile, out_dir)
        except PREPARATION_ERRORS as exc:
            elapsed = time.monotonic() - start
            return self._evidence_error(
                plan, out_dir / f"{plan.render_id}{plan.output_extension}", evidence_file, elapsed, str(exc), ["source-preprocessor"]
            )
        plan = prepared.plan
        resource_roots = prepared.resource_roots
        resource_resolution = prepared.resource_resolution
        cmd_source = prepared.source

        # --- build pandoc command ---
        cmd = ["pandoc", str(cmd_source), "-o", str(compile_pdf)]
        # Every preamble line of this render, in one place (engine/preamble.py).
        preamble = Preamble()
        preamble.add_source(cmd_source)
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
            preamble.add("page_geometry", self._page_geometry_preamble(plan, resolved_profile))
            preamble.add("bound_delivery", self._bound_delivery_header_includes(plan))
        font_runtime_defaults, font_runtime_fallbacks, font_preamble = self._font_runtime_defaults(
            resolved_profile.defaults_stack,
            out_dir,
            plan.render_id,
        )
        preamble.add("font_fallback", font_preamble)
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
        glyph_code_filter = plan.boundary_assertions.get("glyph_code_lua_filter")
        if glyph_code_filter:
            cmd += ["--lua-filter", str(glyph_code_filter)]

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

        # Ornament slots and rails the profile package fills (engine/ornaments.py).
        try:
            ornament_plan = plan_ornaments(resolved_profile.ornaments, resolved_profile.package_dir or Path.cwd())
        except OrnamentError as exc:
            return self._evidence_error(plan, output_pdf, evidence_file, time.monotonic() - start, str(exc), ["ornaments"])
        if ornament_plan is not None:
            if Path(pdf_engine).name != "lualatex":
                return self._evidence_error(
                    plan, output_pdf, evidence_file, time.monotonic() - start,
                    f"profile {resolved_profile.canonical_profile_id} fills ornament slots, which need lualatex "
                    f"(the page-position law runs in LuaTeX); its defaults choose {pdf_engine}",
                    ["ornaments"],
                )
            preamble.add("ornaments", ornament_plan.preamble)
            cmd += ["--lua-filter", str(ornament_plan.filter_path),
                    "--metadata", f"of_ornaments={ornament_filter_metadata(ornament_plan)}"]
        # D4: the chapter-opener contract the profile package declares.
        from engine.openers import OpenerError, filter_metadata as opener_filter_metadata, plan_openers

        try:
            opener_plan = plan_openers(getattr(resolved_profile, "openers", None))
        except OpenerError as exc:
            return self._evidence_error(plan, output_pdf, evidence_file, time.monotonic() - start, str(exc), ["openers"])
        if opener_plan is not None:
            preamble.add("openers", opener_plan.preamble)
            cmd += ["--lua-filter", str(opener_plan.filter_path),
                    "--metadata", f"of_openers={opener_filter_metadata(opener_plan)}"]
        # D3/D5: floating plates the manifest asked for (engine/plates.py).
        plates_ledger = None
        if getattr(plan, "plates", None):
            if Path(pdf_engine).name != "lualatex":
                return self._evidence_error(
                    plan, output_pdf, evidence_file, time.monotonic() - start,
                    f"render.plates needs lualatex (the plate injector runs in LuaTeX); "
                    f"profile {resolved_profile.canonical_profile_id} chooses {pdf_engine}",
                    ["plates"],
                )
            from engine.plates import ledger_path as _plate_ledger_path, preamble_lines as _plate_preamble

            plates_ledger = _plate_ledger_path(out_dir, plan.render_id)
            plates_ledger.unlink(missing_ok=True)
            preamble.add("plates", _plate_preamble())
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

        # Strikeout (2026-09-30). Pandoc lowers ~~text~~ to \\st{} (soul) and relies
        # on its stock template's $if(strikeout)$ block to load the package; the
        # Foundry's imported templates have none, so any document with strikeout
        # failed with "Undefined control sequence \\st" (2026-09-01 keeper-capture
        # proof render). Load pandoc's own package choice for every template when
        # the source contains strikeout.
        strikeout_support = self._source_contains_strikeout(cmd_source, resolved_profile.defaults_stack)
        if strikeout_support:
            preamble.add("strikeout", STRIKEOUT_HEADER.rstrip("\n"))

        if draft:
            preamble.add(
                "draft",
                "% Optical Foundry draft render: image boxes, no image data.\n"
                "\\setkeys{Gin}{draft=true}",
            )

        image_bake_report = None
        if bake_images:
            # Bake BEFORE the compile, from what this render can name: the pandoc
            # input, the template and the defaults, resolved against the roots
            # LaTeX searches. The callback then only reads; see engine/image_bake.
            bake_texts = [cmd_source.read_text(encoding="utf-8", errors="ignore")]
            text_paths: list[Path] = [p for p in [template_path, *resolved_profile.defaults_stack] if p]
            # The Lua filters the defaults declare can name images too (codex0's
            # ornament and rail pools are absolute paths in its filter).
            text_paths += self._declared_lua_filters(
                resolved_profile.defaults_stack, resolved_profile.render_environment.cwd
            )
            for text_path in text_paths:
                if Path(text_path).is_file():
                    bake_texts.append(Path(text_path).read_text(encoding="utf-8", errors="ignore"))
            bake_roots = [
                *(root.path for root in resource_roots),
                *resolved_profile.render_environment.resource_paths,
                resolved_profile.render_environment.cwd,
            ]
            referenced = discover_png_references(bake_texts, bake_roots)
            baked = bake_image_paths(referenced)
            image_bake_report = {
                "mode": "lossless",
                "cache": str(image_bake_cache_dir()),
                "referenced_png": len(referenced),
                "baked_now": baked.baked,
                "already_baked": baked.reused,
                "not_bakeable": baked.skipped,
                "accepted_deviation": IMAGE_BAKE_ACCEPTED_DEVIATION,
            }
            bake_lua = out_dir / f"{plan.render_id}.image_bake.lua"
            bake_lua.write_text(image_bake_lua(), encoding="utf-8")
            preamble.add(
                "image_bake",
                "% Optical Foundry lossless image bake (engine/image_bake.py).\n"
                f"\\directlua{{dofile(\"{bake_lua}\")}}",
            )

        # Defaults for every command the engine emits (engine/template_contract.py);
        # last, so the template's and style packages' own definitions win.
        preamble.add("contract", contract_text())

        # The render's one preamble route. Pandoc drops the source's metadata
        # header-includes once this is given; the Preamble already carries them.
        preamble_file = preamble.write(out_dir, plan.render_id)
        if preamble_file is not None:
            cmd += ["--include-in-header", str(preamble_file)]

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

        # D3: the page ledger rides out of pandoc's temporary compile directory in
        # the PDF's Info dictionary; save it beside the render and strip it.
        if plates_ledger is not None:
            from engine.plates import PlateError, extract_ledger

            try:
                ledger = extract_ledger(compile_pdf)
            except (PlateError, OSError, RuntimeError) as exc:
                return self._evidence_error(plan, compile_pdf, evidence_file, elapsed, str(exc), cmd)
            if ledger is not None:
                plates_ledger.write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8")

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
        # D3: containment re-proved from what shipped, on every render.
        plates_report = None
        if plates_ledger is not None:
            from engine.plates import check_render as _check_plates

            plates_report = _check_plates(out_dir, plan.render_id) or {
                "ok": False, "error": "the render wrote no page ledger", "plates": [], "violations": [], "unplaced": []}
            for v in plates_report.get("violations", []):
                warnings.append(f"plate {v.get('asset')} (owner {v.get('owner')!r}) at folio {v.get('folio')}: {v.get('reason')}")
            if plates_report.get("unplaced"):
                warnings.append("plates never placed: " + ", ".join(plates_report["unplaced"]))
            if plates_report.get("error"):
                warnings.append(plates_report["error"])
            if (plan.plates or {}).get("gate", True):
                validation["checks"]["plate_containment"] = bool(plates_report.get("ok"))
                if not plates_report.get("ok"):
                    validation["status"] = "failed"
            validation["warning_count"] = len(warnings)
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
                **({"plates": plates_report} if plates_report is not None else {}),
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
                "render_mode": "draft" if draft else ("measure" if measure else "full"),
                **({"image_bake": image_bake_report} if image_bake_report else {}),
                **({"strikeout_support": True} if strikeout_support else {}),
                "preamble": preamble.evidence(preamble_file),
                "source_preparation": prepared.record,
                **({"plates": plates_report} if plates_report is not None else {}),
                **({"openers": opener_plan.record} if opener_plan is not None else {}),
                **({"ornaments": ornament_plan.record} if ornament_plan is not None else {}),
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
    def _declared_lua_filters(defaults_stack: Iterable[Path], cwd: Path) -> list[Path]:
        """Lua filter files named under ``filters:`` in the defaults stack."""
        import yaml

        found: list[Path] = []
        for defaults in defaults_stack:
            try:
                data = yaml.safe_load(Path(defaults).read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            for entry in data.get("filters") or [] if isinstance(data, dict) else []:
                path = entry.get("path") if isinstance(entry, dict) else entry
                if isinstance(path, str) and "${.}" in path:
                    path = path.replace("${.}", str(Path(defaults).resolve().parent))
                if isinstance(path, str) and path.endswith(".lua"):
                    candidate = Path(path) if Path(path).is_absolute() else Path(cwd) / path
                    if candidate.is_file():
                        found.append(candidate)
        return found

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
    ) -> tuple[Path | None, list[dict[str, str]], list[str]]:
        """Materialize a render-only font fallback overlay for non-macOS hosts.

        Returns the overlay (font variables only), the fallbacks applied, and the
        preamble lines that re-point the yugen style family at installed fonts;
        those go to the render's ``Preamble`` (engine/preamble.py), not into
        the overlay.

        Several imported profile defaults name macOS fonts such as Helvetica or
        Menlo. The profile resolver records those names as declared system
        fallbacks, but XeTeX/fontspec still needs an actual installed family at
        render time. On Sol/Linux, use installed Noto families through a final
        Pandoc defaults overlay instead of mutating the canonical profile tree.
        """
        requested = PandocRenderer._collect_font_variables(defaults_stack)
        if not requested:
            return None, [], []
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

        header_includes: list[str] = []
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

        if not variables:
            return None, fallbacks, header_includes
        path = out_dir / f"{render_id}.font_fallbacks.yaml"
        import yaml
        path.write_text(
            yaml.safe_dump({"variables": variables}, sort_keys=False),
            encoding="utf-8",
        )
        return path, fallbacks, header_includes

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
        variables: dict[str, Any] = {"geometry": geometry}
        if plan.delivery.get("mode") == "bound":
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
    def _page_geometry_preamble(plan: ProjectionPlan, resolved_profile: ResolvedProfile) -> list[str]:
        """Preamble lines that go with the page-geometry overlay.

        XeTeX can emit a letter MediaBox unless the paper special follows
        geometry. Bound-delivery pagestyles and rails ride the same condition
        (a requested page geometry), as they did when both lived in the overlay.
        """
        if not PandocRenderer._page_geometry_options(plan, resolved_profile):
            return []
        return [r"\special{papersize=\the\paperwidth,\the\paperheight}"]

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
        return source_header_includes(render_source)

    @staticmethod
    def _source_contains_strikeout(render_source: Path, defaults_stack: Iterable[Path]) -> bool:
        """True when pandoc, reading ``render_source`` as the profile does, finds strikeout.

        Exact rather than textual: a ``~~`` inside code, a comment, or a field the
        document never renders must not load the strikeout packages (luacolor
        changes how LuaTeX writes colour). Pandoc is consulted only when the text
        contains ``~~``; if it cannot be run, fall back to including the packages.
        """
        if not render_source.exists():
            return False
        if "~~" not in render_source.read_text(encoding="utf-8", errors="ignore"):
            return False
        reader = "markdown"
        for defaults_file in defaults_stack:
            try:
                import yaml

                data = yaml.safe_load(Path(defaults_file).read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if isinstance(data, dict) and isinstance(data.get("from"), str):
                reader = data["from"]
        try:
            result = subprocess.run(
                ["pandoc", "-f", reader, "-t", "json", str(render_source)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True
        if result.returncode != 0:
            return True
        return '"t":"Strikeout"' in result.stdout

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
            if key == "titlepage_background_image" and not safe_frontmatter_resource_path(value):
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
