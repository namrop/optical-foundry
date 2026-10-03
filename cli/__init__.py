#!/usr/bin/env python3
"""Optical Foundry CLI — render Markdown or manifest inputs through Pandoc.

Usage:
    python -m cli.render doc <input.md> --profile risk [--output outdir]
    python -m cli.render manifest <manifest.yaml> [--output outdir]

This is a Phase 1 reference CLI. It wires the manifest compilation and
Pandoc render dispatch pipeline end-to-end.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure greenfield root is on sys.path so engine/renderers resolve.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.manifest_registry import ManifestRegistry
from engine.manifest_compiler import (
    CompositeBundleCompiler,
    CAMStackCompiler,
    CodexBundleCompiler,
    MarkdownDocumentCompiler,
    LabelRunCompiler,
    StickerSheetCompiler,
    ForgePacketReviewCompiler,
)
from renderers.pandoc_renderer import PandocRenderer
from renderers.document_renderer import DocumentRenderer
from engine.imposition import ImpositionError, impose_pdf
from engine.bind_shape import BindShapeError, pad_to_signature
from engine.build_stamp import distinct_stamps
from engine.pass_gates import compare_renders
from engine.profile_checker import check_all_profiles, check_all_profiles_json, check_profile
from engine.profile_smoke import DEFAULT_DOCUMENT_SMOKE_PROFILES, run_profile_smoke_matrix
from engine.visual_proof import build_visual_proof, compare_contact_sheets
from engine.dropcap_assets import analyze_dropcap_alpha_bounds
from engine.layout_images import image_initial_recipes


def _default_registry() -> ManifestRegistry:
    reg = ManifestRegistry()
    for cls in [CompositeBundleCompiler, CAMStackCompiler, CodexBundleCompiler, MarkdownDocumentCompiler, LabelRunCompiler, StickerSheetCompiler, ForgePacketReviewCompiler]:
        reg.register(cls.kind, cls.schema_version, cls)
    return reg


def cmd_doc(args: argparse.Namespace) -> int:
    dr = DocumentRenderer()
    evidence = dr.render(Path(args.input), args.profile, output_dir=args.output)
    success = evidence.get("status") != "error"
    print(json.dumps({"status": "ok" if success else "error",
                       "render_id": evidence.get("render_id", "?"),
                       "output": evidence.get("output", {}).get("pdf_path", "unknown"),
                       "pages": evidence.get("output", {}).get("pdf_pages", 0),
                       "error": evidence.get("error", "")}, indent=2))
    return 0 if success else 1


def _parse_yaml_file(path: Path) -> dict:
    """Parse a YAML file, falling back to a minimal parser if yaml is unavailable."""
    try:
        import yaml
        return yaml.safe_load(path.read_text())
    except ImportError:
        return _parse_minimal_yaml(path.read_text())


def _parse_minimal_yaml(text: str) -> dict:
    """Minimal YAML parser for Optical Foundry manifest envelopes.

    Handles scalars, nested maps, lists-of-maps, and comments.
    Does not support anchors, aliases, tags, multi-line strings, or flow style.
    Sufficient for all 6 manifest subtypes.
    """
    lines = text.splitlines()
    # Pre-process: build a list of (indent, line) for non-empty, non-comment lines
    items = []
    for raw in lines:
        s = raw.rstrip()
        if not s or s.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        items.append((indent, s.strip()))

    result: dict = {}
    # stack entries: (indent, container, key_if_pending_or_None)
    # A "pending" key means the last line was "key:" with no value, and we're
    # waiting for child content to know whether it's a map or list.
    stack: list[tuple[int, dict | list, str | None]] = [(-1, result, None)]

    def _resolve_pending(parent: dict, key: str, parent_indent: int, start_idx: int) -> dict | list:
        """Look ahead from start_idx to decide whether pending key should become a dict or list."""
        # Only scan items after the current position
        for ci, cl in items[start_idx:]:
            if ci > parent_indent:
                # The first deeper line after this key determines the type
                return [] if cl.startswith('- ') else {}
        return {}

    for idx, (indent, stripped) in enumerate(items):
        # Pop stack until we find a parent with lower indent
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent_indent, parent, pending = stack[-1]

        # List item
        if stripped.startswith('- '):
            val = stripped[2:].strip()
            # Parent must be a dict with a pending key, or already a list
            if isinstance(parent, list):
                if ':' in val:
                    # List-of-maps item: "- key: value"
                    k, _, v = val.partition(':')
                    child: dict = {k.strip(): _coerce_scalar(v.strip())}
                    parent.append(child)
                    stack.append((indent, child, None))
                else:
                    # Simple scalar list item: "- value"
                    parent.append(_coerce_scalar(val))
            elif isinstance(parent, dict) and pending is not None:
                # pending key becomes a list
                lst: list = []
                parent[pending] = lst
                stack[-1] = (parent_indent, parent, None)
                if ':' in val:
                    k, _, v = val.partition(':')
                    child: dict = {k.strip(): _coerce_scalar(v.strip())}
                    lst.append(child)
                    stack.append((indent, child, None))
                else:
                    lst.append(_coerce_scalar(val))
            continue

        # Key: value or Key:
        if ':' in stripped:
            key, _, val = stripped.partition(':')
            key = key.strip()
            val = val.strip()

            if isinstance(parent, dict):
                if val == '' or val == '{}':
                    # Pending — value type determined by children
                    child = _resolve_pending(parent, key, indent, idx + 1)
                    parent[key] = child
                    stack.append((indent, child, key))
                else:
                    parent[key] = _coerce_scalar(val)
            elif isinstance(parent, list):
                # Shouldn't happen with valid manifests, but handle gracefully
                child = {key: _coerce_scalar(val) if val else {}}
                parent.append(child)
                stack.append((indent, child, key if not val else None))

    return result


def _coerce_scalar(val: str):
    """Coerce a YAML scalar value to bool, int, float, or str."""
    if val in ('true', 'True', 'TRUE', 'yes', 'Yes'):
        return True
    if val in ('false', 'False', 'FALSE', 'no', 'No'):
        return False
    if val in ('null', '~', ''):
        return None
    # quoted string
    if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
        return val[1:-1]
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def cmd_manifest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.input)
    raw = _parse_yaml_file(manifest_path)

    reg = _default_registry()
    compiler_cls = reg.resolve_compiler(raw)
    if compiler_cls is None:
        print(f"ERROR: no compiler for kind={raw.get('kind')} schema_version={raw.get('schema_version')}", file=sys.stderr)
        return 1

    compiler = compiler_cls()
    errors = compiler.validate(raw)
    if errors:
        for err in errors:
            print(f"VALIDATION ERROR: {err}", file=sys.stderr)
        return 1

    if raw.get("volumes"):
        # A work in several volumes: split, seat the folios, and add the
        # contents of the work if asked (engine/volumes.py, map B1/B2).
        from engine.volumes import VolumeError, render_volumes

        volume_kwargs = {k: True for k in ("measure", "bake_images") if getattr(args, k, False)}
        try:
            report = render_volumes(raw, Path(args.output), manifest_path=manifest_path.resolve(),
                                    draft=bool(getattr(args, "draft", False)), **volume_kwargs)
        except (VolumeError, ValueError) as exc:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
            return 1
        print(json.dumps({
            "status": "ok",
            "report": report["report_path"],
            "volumes": [{"id": v["id"], "output": v["pdf"], "pages": v["pages"],
                         "folios": f"{v['first_body_folio']}-{v['last_body_folio']}"} for v in report["volumes"]],
            "work_contents_rows": (report.get("work_contents") or {}).get("rows", 0),
        }, indent=2))
        return 0

    try:
        plan = compiler.compile(raw, manifest_path=manifest_path.resolve())
    except ValueError as exc:
        print(f"VALIDATION ERROR: {exc}", file=sys.stderr)
        return 1
    renderer = PandocRenderer()
    # Pass `measure` only when asked for, so renderers written to the base
    # signature (and callers that build their own Namespace) keep working.
    render_kwargs = {}
    if getattr(args, "measure", False):
        render_kwargs["measure"] = True
    if getattr(args, "draft", False):
        render_kwargs["draft"] = True
    if getattr(args, "bake_images", False):
        render_kwargs["bake_images"] = True
    evidence = renderer.render(plan, output_dir=args.output, **render_kwargs)
    success = evidence.get("status") != "error"
    print(json.dumps({"status": "ok" if success else "error",
                       "render_id": evidence.get("render_id", "?"),
                       "output": evidence.get("output", {}).get("pdf_path", "unknown"),
                       "pages": evidence.get("output", {}).get("pdf_pages", 0),
                       "error": evidence.get("error", "")}, indent=2))
    return 0 if success else 1


def cmd_initial(args: argparse.Namespace) -> int:
    """Inspect and list illuminated image-initial tuning surfaces."""
    if args.initial_command == "recipes":
        print(json.dumps({"recipes": image_initial_recipes()}, indent=2, sort_keys=True))
        return 0
    if args.initial_command == "inspect":
        report = analyze_dropcap_alpha_bounds(Path(args.input), alpha_threshold=args.alpha_threshold)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("status") == "ok" else 1
    print("ERROR: initial subcommand required", file=sys.stderr)
    return 1


def cmd_proof(args: argparse.Namespace) -> int:
    """Generate visual proof artifacts for rendered PDFs."""
    if args.proof_command == "compare":
        result = compare_contact_sheets(
            Path(args.baseline), Path(args.candidate), output_dir=Path(args.output), label=args.label
        )
        if result["identical"]:
            print(f"{args.label}: {result['candidate_pages']} pages, contact sheets identical")
            return 0
        if result["baseline_pages"] != result["candidate_pages"]:
            print(f"{args.label}: page count {result['baseline_pages']} != {result['candidate_pages']}", file=sys.stderr)
        else:
            edge = result.get("edge_only_pages", [])
            if edge:
                print(f"{args.label}: MARKED {len(edge)} page(s) differ only at image edges — embedded image data, "
                      f"placement and text identical (accepted deviation, ruling 01a0eb4f-849e): {edge[:30]}")
            substantive = result.get("substantive_pages", result["differing_pages"])
            if not substantive:
                return 0
            print(f"{args.label}: {len(substantive)} page(s) differ: {substantive[:30]} "
                  f"(sheet: {result['diff_sheet']})", file=sys.stderr)
        return 1
    if args.proof_command != "contact-sheet":
        print("ERROR: proof subcommand required", file=sys.stderr)
        return 1
    proof = build_visual_proof(
        Path(args.input),
        output_dir=Path(args.output),
        max_pages=args.max_pages,
        columns=args.columns,
        dpi=args.dpi,
    )
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0 if proof.get("status") == "ok" else 1


def cmd_smoke(args: argparse.Namespace) -> int:
    """Run smoke matrices for render/profile behavior."""
    if args.smoke_command != "profiles":
        print("ERROR: smoke subcommand required", file=sys.stderr)
        return 1
    profiles = args.profile or list(DEFAULT_DOCUMENT_SMOKE_PROFILES)
    summary = run_profile_smoke_matrix(
        profiles=profiles,
        fixture=args.fixture,
        output_dir=args.output,
        create_proofs=args.proof,
        proof_max_pages=args.proof_max_pages,
        proof_columns=args.proof_columns,
        proof_dpi=args.proof_dpi,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "passed" else 1


def cmd_profiles(args: argparse.Namespace) -> int:
    """Check and report profile capabilities."""
    if args.json:
        print(check_all_profiles_json())
        return 0

    if args.profile:
        cap = check_profile(args.profile)
        _print_profile_table_row(cap)
        return 0

    # Print table for all profiles
    caps = check_all_profiles()
    _print_profiles_table(caps)
    return 0


def cmd_impose(args: argparse.Namespace) -> int:
    """Impose a rendered PDF into booklet/signature sheet sides."""
    try:
        result = impose_pdf(
            Path(args.input),
            output=args.output,
            page_size=args.page_size,
            sheet_size=args.sheet_size,
            signature_size=args.signature_size,
            duplex_mode=args.duplex,
            gutter_bias_mm=args.gutter_bias_mm,
        )
    except ImpositionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "ok",
        "layout": "booklet_signature_2up",
        "input": str(Path(args.input).expanduser().resolve()),
        "output": str(result.output_pdf),
        "mapping": str(result.mapping_json),
        "page_size": args.page_size.replace("-", "_").replace(" ", "_"),
        "sheet_size": args.sheet_size.replace("-", "_").replace(" ", "_"),
        "signature_size": int(args.signature_size),
        "duplex_mode": args.duplex.replace("-", "_").replace(" ", "_"),
        "input_pages": result.input_pages,
        "output_pages": result.output_pages,
        "padded_pages": result.padded_pages,
        "blank_count": result.blank_count,
    }, indent=2))
    return 0


def _print_profiles_table(caps: dict) -> None:
    """Pretty-print a table of all profile capabilities."""
    # Header
    hdr = f"{'Profile':<28} {'D':<2} {'Src':<6} {'T':<2} {'Src':<6} {'TOC':<5} {'Bundle':<14} {'Notes'}"
    print(hdr)
    print("-" * len(hdr))

    # Legend
    print("L=local(import)  R=40_latex(reference)  D=Defaults  T=Template")
    print()

    badge = {"ok": "✅ ok", "partial": "⚠️  partial", "incompatible": "❌ incompatible"}

    for pid, cap in sorted(caps.items()):
        has_d = "✓" if cap.defaults_found else "✗"
        has_t = "✓" if cap.template_found else "✗"
        has_toc = "✓" if cap.supports_toc else "✗"
        ds = cap.defaults_source[:1].upper() if cap.defaults_source != "missing" else "-"
        ts = cap.template_source[:1].upper() if cap.template_source != "missing" else "-"
        b = badge.get(cap.bundle_compatibility, cap.bundle_compatibility)
        reasons = "; ".join(cap.bundle_reasons[:1])  # first reason
        print(f"{pid:<28} {has_d} {ds:<6} {has_t} {ts:<6} {has_toc:<5} {b:<14} {reasons}")

    # Summary
    from engine.profile_checker import _build_summary
    s = _build_summary(caps)
    print()
    print(f"Total: {s['total']} | Bundle: {s['bundle_ok']} ok, {s['bundle_partial']} partial, "
          f"{s['bundle_incompatible']} incompatible | "
          f"Defaults: {s['with_defaults']}/{s['total']} (L:{s.get('defaults_local',0)} R:{s.get('defaults_40_latex',0)}) | "
          f"Templates: {s['with_templates']}/{s['total']} (L:{s.get('templates_local',0)} R:{s.get('templates_40_latex',0)}) | "
          f"TOC: {s['with_toc_support']}/{s['total']}")


def _print_profile_table_row(cap: "ProfileCapability") -> None:
    """Pretty-print a single profile check."""
    print(f"Profile: {cap.profile_id}")
    print(f"  Defaults:    {cap.defaults_found or 'MISSING'}  (source: {cap.defaults_source})")
    print(f"  Template:    {cap.template_found or 'MISSING'}  (source: {cap.template_source}, inferred: {cap.template_inferred})")
    print(f"  Uses external profile ref: {cap.uses_legacy_profile_tree}")
    print(f"  TOC support:   {cap.supports_toc}")
    print(f"  Tightlist:     {cap.has_tightlist}")
    print(f"  Longtable:     {cap.has_longtable}")
    print(f"  Bundle compat: {cap.bundle_compatibility}")
    if cap.bundle_reasons:
        for r in cap.bundle_reasons:
            print(f"    → {r}")
    if cap.warnings:
        for w in cap.warnings:
            print(f"  ⚠  {w}")


def cmd_bind_shape(args: argparse.Namespace) -> int:
    """Pad rendered PDFs to whole signatures, writing <name>_bind.pdf beside each."""
    status = 0
    for item in args.input:
        try:
            result = pad_to_signature(
                Path(item),
                args.signature_size,
                blank_mark=Path(args.blank_mark) if args.blank_mark else None,
                mark_width_fraction=args.mark_width,
            )
        except BindShapeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            status = 1
            continue
        print(f"  {result.summary()}")
    return status


def cmd_stamps_agree(args: argparse.Namespace) -> int:
    """One build, one stamp: every file must carry the same stamp line."""
    stamps = distinct_stamps([Path(p) for p in args.input], args.pattern)
    if len(stamps) != 1:
        print(f"ERROR: the artifacts do not share one render stamp ({len(stamps)} distinct):", file=sys.stderr)
        for line in stamps:
            print(f"    {line}", file=sys.stderr)
        return 65
    print(stamps[0])
    return 0


def cmd_renders_agree(args: argparse.Namespace) -> int:
    """Two renders of one bundle must have the same shape (count, labels, outline)."""
    diffs = compare_renders(Path(args.reference), Path(args.candidate))
    if diffs:
        print(f"ERROR: {Path(args.candidate).name} does not match {Path(args.reference).name}:", file=sys.stderr)
        for d in diffs:
            print(f"    {d}", file=sys.stderr)
        return 66
    print(f"  same shape: {Path(args.candidate).name} == {Path(args.reference).name} (pages, every label, outline)")
    return 0


def _glyph_paths(items: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in items:
        path = Path(item)
        paths.extend(sorted(path.rglob("*.md")) if path.is_dir() else [path])
    return paths


def cmd_glyphs(args: argparse.Namespace) -> int:
    """Report (scan) or vendor (grow) the glyphs a set of sources needs."""
    from engine import glyph_registry as gr

    coverage_fonts = [Path(f) for f in (args.coverage_font or [])] or gr.default_coverage_fonts()
    covered = gr.font_coverage(coverage_fonts)
    registry = gr.load_registry()
    noto = Path(args.noto_source) if args.noto_source else None
    noto_keys = gr.noto_svg_keys(noto) if noto else None
    paths = _glyph_paths(args.input)
    symbol_faces = gr.default_symbol_faces()
    symbol_coverage = gr.font_coverage(symbol_faces.values()) if symbol_faces else set()
    needs = gr.scan_needed(
        paths, covered=covered, registry=registry, noto_keys=noto_keys,
        symbol_coverage=symbol_coverage, code_covered=gr.monospace_coverage(),
    )

    def show(title: str, table: dict, label) -> None:
        if not table:
            return
        print(f"{title}:")
        for key, entry in sorted(table.items(), key=lambda kv: -len(kv[1]["files"])):
            print(f"  {label(key)}  {entry['count']}x in {len(entry['files'])} file(s)")

    import unicodedata

    def cp_label(cp: int) -> str:
        return f"U+{cp:04X} {chr(cp)} {unicodedata.name(chr(cp), '?')}"

    def emoji_label(key: str) -> str:
        seq = gr.key_sequence(key)
        return f"{key} {''.join(chr(c) for c in seq)} {unicodedata.name(chr(seq[0]), '?')}"

    print(f"{len(paths)} file(s); coverage fonts: {', '.join(str(f) for f in coverage_fonts)}")
    show("emoji to vendor", needs.emoji, emoji_label)
    show("CJK fallback-font characters", needs.fallback, cp_label)
    show("symbols fallback-font characters", needs.symbols, cp_label)
    show("not resolvable here" + ("" if noto else " (pass --noto-source to match emoji)"), needs.unresolved, cp_label)
    if args.glyphs_command == "scan":
        return 1 if (needs.emoji or needs.fallback or needs.symbols or needs.unresolved) else 0

    if needs.emoji and not noto:
        print("ERROR: --noto-source is required to vendor emoji", file=sys.stderr)
        return 2
    for key in sorted(needs.emoji):
        registry["emoji"][key] = gr.vendor_emoji(key, noto, noto_version=args.noto_version)
        print(f"  vendored {key}")
    if needs.fallback:
        if not args.cjk_font:
            print("ERROR: --cjk-font is required for fallback-font characters", file=sys.stderr)
            return 2
        fonts = registry["fallback_fonts"]
        family = next((f for f in fonts if f["family"] == "OFFallbackCJK"), None)
        if family is None:
            family = {"family": "OFFallbackCJK", "codepoints": []}
            fonts.append(family)
        codepoints = {int(cp) for cp in family["codepoints"]} | set(needs.fallback)
        faces = {"Regular": (Path(args.cjk_font), args.cjk_font_number)}
        if args.cjk_font_bold:
            faces["Bold"] = (Path(args.cjk_font_bold), args.cjk_font_number)
        updated = gr.subset_fallback_font(family, codepoints, faces=faces)
        updated["source"] = args.cjk_source_label
        updated["license"] = "OFL-1.1"
        fonts[fonts.index(family)] = updated
        print(f"  OFFallbackCJK now covers {len(codepoints)} code point(s)")
    if needs.symbols:
        fonts = registry["fallback_fonts"]
        family = next((f for f in fonts if f["family"] == "OFFallbackSymbols"), None)
        if family is None:
            family = {"family": "OFFallbackSymbols", "codepoints": []}
            fonts.append(family)
        codepoints = {int(cp) for cp in family["codepoints"]} | set(needs.symbols)
        faces = {face: (path, 0) for face, path in symbol_faces.items()}
        updated = gr.subset_fallback_font(family, codepoints, faces=faces)
        updated["source"] = "DejaVu Sans 2.37 (TeX Live dejavu package)"
        updated["license"] = "Bitstream Vera / DejaVu (free; see dejavu LICENSE)"
        fonts[fonts.index(family)] = updated
        print(f"  OFFallbackSymbols now covers {len(codepoints)} code point(s)")
    gr.save_registry(registry)
    if needs.unresolved:
        print("WARNING: some characters have no registry source; the render lint will still refuse them", file=sys.stderr)
        return 3
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    """A2: compose a bundle manifest from a selection file."""
    from engine.selection import SelectionError, emit

    try:
        out, result = emit(Path(args.input), Path(args.output) if args.output else None)
    except SelectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    info = result.manifest["selection"]
    print(f"Wrote {out}")
    print(f"  {info['selected']} source(s), {len(result.manifest['section_dividers'])} divider(s); "
          f"{info['excluded_by_predicate']} excluded by predicate")
    print(f"  dates: {info['date_origins']}  titles: {info['title_origins']}")
    if args.verbose:
        for path, reason in result.excluded:
            print(f"  excluded {path.name}: {reason}")
    return 0


def cmd_print_sheet(args: argparse.Namespace) -> int:
    from engine.print_sheet import PrintSheetError, render as render_print_sheet

    try:
        ev = render_print_sheet(Path(args.input), Path(args.output) if args.output else None)
    except PrintSheetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({k: ev[k] for k in ("status", "sheet_id", "output")}, indent=2))
    return 0


def cmd_duplex(args: argparse.Namespace) -> int:
    import yaml as _yaml

    from engine.duplex_registration import SHEETS, DuplexError, Station, default_stations, render_instrument, summarize

    try:
        if args.duplex_command == "instrument":
            if args.sheet not in SHEETS:
                raise DuplexError(f"--sheet must be one of {sorted(SHEETS)}")
            w, h = SHEETS[args.sheet]
            if args.stations:
                raw = _yaml.safe_load(Path(args.stations).read_text(encoding="utf-8")) or []
                stations = [Station(str(r["label"]), float(r["x"]), float(r["y"]), bool(r.get("cross"))) for r in raw]
            else:
                stations = default_stations(w, h)
            out = render_instrument(Path(args.output), stations=stations, width=w, height=h, scale_mm=args.scale_mm)
            print(f"wrote {out}: {len(stations)} stations; print page 1 on the front, page 2 on the back")
            return 0
        if args.duplex_command == "readings":
            readings = _yaml.safe_load(Path(args.input).read_text(encoding="utf-8")) or []
            deciding = [x.strip() for x in args.deciding.split(",")] if args.deciding else None
            print(json.dumps(summarize(readings, deciding=deciding), indent=2))
            return 0
    except DuplexError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("duplex: choose instrument or readings", file=sys.stderr)
    return 2


def cmd_bindery(args: argparse.Namespace) -> int:
    import json as _json

    from engine.bindery import (BinderyError, folio_run_report, press_sheet_map, punch_guide_svg,
                                sewing_stations)

    if args.bindery_command == "folio-run":
        failed = 0
        for pdf in args.input:
            rep = folio_run_report(Path(pdf))
            if rep["ok"]:
                print(f"  {Path(pdf).name}: {rep['numbered']} numbered pages, run {rep['run'][0]}..{rep['run'][1]}, parity matches")
            else:
                failed += 1
                for line in rep["problems"]:
                    print(f"ERROR {Path(pdf).name}: {line}", file=sys.stderr)
        return 1 if failed else 0
    if args.bindery_command == "sheet-map":
        sets = {}
        for item in args.set:
            name, _, nums = item.partition("=")
            sets[name.strip()] = [int(x) for x in nums.split(",") if x.strip()]
        try:
            data = press_sheet_map(Path(args.input), args.signature_size, duplex=args.duplex.replace("-", "_"),
                                   sheet_sets=sets)
        except BinderyError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        for w in data["warnings"]:
            print(f"WARNING: {w}", file=sys.stderr)
        text = _json.dumps(data, indent=1)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
            print(f"wrote {args.output}: {data['sheets']} sheets, {len(data['folio_to_sheet'])} folios indexed")
        else:
            print(text)
        return 0
    if args.bindery_command == "punch-guide":
        stations = sewing_stations(fold_height_in=args.fold_height, kettle_offset_in=args.kettle_offset,
                                   tapes=args.tapes, tape_width_in=args.tape_width)
        Path(args.output).write_text(punch_guide_svg(stations, fold_height_in=args.fold_height), encoding="utf-8")
        for st in stations:
            print(f"  {st.number}  {st.from_head_in:.6f} in  {st.from_head_in * 25.4:8.3f} mm  {st.role}")
        return 0
    print("bindery: choose folio-run, sheet-map or punch-guide", file=sys.stderr)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(prog="foundry", description="Optical Foundry CLI")
    sub = ap.add_subparsers(dest="command")

    # doc
    doc_ap = sub.add_parser("doc", help="Render a Markdown document")
    doc_ap.add_argument("input", help="Markdown file path")
    doc_ap.add_argument("--profile", required=True)
    doc_ap.add_argument("--output", default="generated/documents")
    doc_ap.set_defaults(func=cmd_doc)

    # manifest
    mf_ap = sub.add_parser("manifest", help="Render from a manifest YAML")
    mf_ap.add_argument("input", help="Manifest YAML file path")
    mf_ap.add_argument("--output", default="generated/manifests")
    mf_ap.add_argument(
        "--measure",
        action="store_true",
        help=("Measurement render for a later pass (page labels, extent): skip imposition "
              "and the bindery preflight / safe-area overlay; evidence records render_mode: measure"),
    )
    mf_ap.add_argument(
        "--draft",
        action="store_true",
        help=("Draft render (implies --measure): graphicx draft, image boxes without image data. "
              "Same pagination, labels, text and outline; not a deliverable"),
    )
    mf_ap.add_argument(
        "--bake-images",
        action="store_true",
        help=("Lossless image bake (LuaLaTeX): alpha PNGs the render names are pre-split once into a cache "
              "and embedded by copy. Same embedded image data"),
    )
    mf_ap.set_defaults(func=cmd_manifest)

    # profiles
    pf_ap = sub.add_parser("profiles", help="Check profile capabilities and bundle compatibility")
    pf_ap.add_argument("--json", action="store_true", help="Output full JSON report")
    pf_ap.add_argument("--profile", help="Check a single profile")
    pf_ap.set_defaults(func=cmd_profiles)

    # smoke
    smoke_ap = sub.add_parser("smoke", help="Run render smoke matrices")
    smoke_sub = smoke_ap.add_subparsers(dest="smoke_command")
    smoke_profiles_ap = smoke_sub.add_parser("profiles", help="Render a generated fixture across selected profiles")
    smoke_profiles_ap.add_argument("--fixture", choices=["basic", "illuminated-initial"], default="basic")
    smoke_profiles_ap.add_argument("--profile", action="append", help="Profile to test; repeat to test multiple profiles")
    smoke_profiles_ap.add_argument("--output", default="generated/profile_smoke_matrix")
    smoke_profiles_ap.add_argument("--proof", action="store_true", help="Generate visual proof contact sheets for passed renders")
    smoke_profiles_ap.add_argument("--proof-max-pages", type=int, default=12)
    smoke_profiles_ap.add_argument("--proof-columns", type=int, default=3)
    smoke_profiles_ap.add_argument("--proof-dpi", type=int, default=120)
    smoke_profiles_ap.set_defaults(func=cmd_smoke)

    # initial
    initial_ap = sub.add_parser("initial", help="Inspect and tune illuminated image initials")
    initial_sub = initial_ap.add_subparsers(dest="initial_command")
    initial_recipes_ap = initial_sub.add_parser("recipes", help="List named of-initial tuning recipes")
    initial_recipes_ap.set_defaults(func=cmd_initial)
    initial_inspect_ap = initial_sub.add_parser("inspect", help="Inspect PNG alpha bounds for drop-cap cropping")
    initial_inspect_ap.add_argument("input", help="Drop-cap PNG path")
    initial_inspect_ap.add_argument("--alpha-threshold", type=int, default=0)
    initial_inspect_ap.set_defaults(func=cmd_initial)

    # proof
    proof_ap = sub.add_parser("proof", help="Generate visual proof artifacts for rendered PDFs")
    proof_sub = proof_ap.add_subparsers(dest="proof_command")
    contact_ap = proof_sub.add_parser("contact-sheet", help="Rasterize a PDF and create a labeled SVG contact sheet")
    contact_ap.add_argument("input", help="Rendered PDF path")
    contact_ap.add_argument("--output", default="generated/proofs/contact_sheet")
    contact_ap.add_argument("--max-pages", type=int, default=12)
    contact_ap.add_argument("--columns", type=int, default=3)
    contact_ap.add_argument("--dpi", type=int, default=120)
    contact_ap.set_defaults(func=cmd_proof)
    compare_ap = proof_sub.add_parser(
        "compare", help="Compare two PDFs by full contact sheet (every page); exit 1 unless identical"
    )
    compare_ap.add_argument("baseline", help="Baseline PDF")
    compare_ap.add_argument("candidate", help="Candidate PDF")
    compare_ap.add_argument("--output", default="generated/proofs/compare", help="Directory for the sheets")
    compare_ap.add_argument("--label", default="compare", help="File-name prefix for the sheets")
    compare_ap.set_defaults(func=cmd_proof)

    # impose
    im_ap = sub.add_parser("impose", help="Impose a rendered PDF into booklet/signature sheets")
    im_ap.add_argument("input", help="Input PDF path")
    im_ap.add_argument("--output", default="generated/impositions", help="Output directory or final .pdf path")
    im_ap.add_argument("--page-size", required=True, help="Input page size, e.g. half_letter")
    im_ap.add_argument("--sheet-size", required=True, help="Printer sheet size, e.g. letter")
    im_ap.add_argument("--signature-size", required=True, type=int, help="Pages per folded signature; must be a multiple of 4")
    im_ap.add_argument(
        "--duplex",
        required=True,
        choices=["short-edge", "short_edge", "long-edge", "long_edge"],
        help="Printer duplex mode; short-edge is typical for landscape booklet sheets",
    )
    im_ap.add_argument(
        "--gutter-bias-mm",
        type=float,
        default=0.0,
        help=("Nudge each imposed page outward toward its outer sheet edge by this many mm "
              "so printer shortfall lands in the center gutter (hidden in the bind), not the "
              "fore-edges. Use for plate/divider sheets (e.g. 1.0); 0 (default) for text sheets."),
    )
    im_ap.set_defaults(func=cmd_impose)

    # bind-shape
    bs_ap = sub.add_parser("bind-shape", help="Pad rendered PDFs to whole signatures (<name>_bind.pdf)")
    bs_ap.add_argument("input", nargs="+", help="Rendered PDF path(s)")
    bs_ap.add_argument("--signature-size", required=True, type=int, help="Pages per folded signature; multiple of 4")
    bs_ap.add_argument("--blank-mark", help="Image placed centred on every pad leaf")
    bs_ap.add_argument("--mark-width", type=float, default=0.2, help="Mark width as a fraction of page width (default 0.2)")
    bs_ap.set_defaults(func=cmd_bind_shape)

    # bindery (map E2)
    bd_ap = sub.add_parser("bindery", help="Bindery checks and guides: folio runs, press sheet maps, punching guides")
    bd_sub = bd_ap.add_subparsers(dest="bindery_command")
    fr = bd_sub.add_parser("folio-run", help="Exit 1 unless each PDF's folios are one arabic run with matching parity")
    fr.add_argument("input", nargs="+", help="Rendered volume PDF(s)")
    fr.set_defaults(func=cmd_bindery)
    sm = bd_sub.add_parser("sheet-map", help="Map a bind PDF onto press sheets (JSON)")
    sm.add_argument("input", help="The _bind.pdf (cli bind-shape)")
    sm.add_argument("--signature-size", required=True, type=int)
    sm.add_argument("--duplex", default="short-edge", choices=["short-edge", "short_edge", "long-edge", "long_edge"])
    sm.add_argument("--set", action="append", default=[], metavar="NAME=1,2,3",
                    help="A ruled sheet set (e.g. cover=1,5,6); repeatable")
    sm.add_argument("--output", help="JSON path (default: stdout)")
    sm.set_defaults(func=cmd_bindery)
    pg = bd_sub.add_parser("punch-guide", help="Exact-scale sewing-station punching strip (SVG)")
    pg.add_argument("--fold-height", required=True, type=float, help="Inches")
    pg.add_argument("--kettle-offset", required=True, type=float, help="Inches from head and tail")
    pg.add_argument("--tapes", required=True, type=int)
    pg.add_argument("--tape-width", required=True, type=float, help="Inches")
    pg.add_argument("--output", required=True, help="SVG path")
    pg.set_defaults(func=cmd_bindery)

    # print-sheet (map E3)
    ps_ap = sub.add_parser("print-sheet", help="Place labels/cards at exact physical sizes on one sheet (kind: print_sheet)")
    ps_ap.add_argument("input", help="print_sheet_v1 manifest YAML")
    ps_ap.add_argument("--output", help="PDF path or directory (default: beside the manifest)")
    ps_ap.set_defaults(func=cmd_print_sheet)

    # duplex (map E4)
    dx_ap = sub.add_parser("duplex", help="Duplex registration: print the instrument, summarize readings")
    dx_sub = dx_ap.add_subparsers(dest="duplex_command")
    di = dx_sub.add_parser("instrument", help="Two-page marks-only instrument (front lines, mirrored back scales)")
    di.add_argument("--sheet", default="letter-landscape", help="letter-landscape | letter | a4-landscape | a4")
    di.add_argument("--stations", help="YAML list of {label, x, y, cross} in inches (default: 3 per half)")
    di.add_argument("--scale-mm", type=int, default=10)
    di.add_argument("--output", required=True, help="PDF path")
    di.set_defaults(func=cmd_duplex)
    dr = dx_sub.add_parser("readings", help="Summarize readings (YAML list of {sheet, station, dx_mm, dy_mm})")
    dr.add_argument("input")
    dr.add_argument("--deciding", help="Comma-separated stations whose mean is the number to seat")
    dr.set_defaults(func=cmd_duplex)

    # stamps-agree
    sa_ap = sub.add_parser("stamps-agree", help="Fail unless every file carries one identical build-stamp line")
    sa_ap.add_argument("input", nargs="+", help="Files to scan (e.g. resolved sources of every volume)")
    sa_ap.add_argument("--pattern", required=True, help="Regex matching the stamp line")
    sa_ap.set_defaults(func=cmd_stamps_agree)

    # renders-agree
    ra_ap = sub.add_parser("renders-agree", help="Fail unless two renders of one bundle have the same pages, labels and outline")
    ra_ap.add_argument("reference", help="The render a later pass read (e.g. the draft)")
    ra_ap.add_argument("candidate", help="The render that ships")
    ra_ap.set_defaults(func=cmd_renders_agree)

    # select
    sel_ap = sub.add_parser("select", help="Compose a bundle manifest from a selection file (A2)")
    sel_ap.add_argument("input", help="Selection YAML (kind: selection)")
    sel_ap.add_argument("--output", help="Bundle manifest to write (default: the file's emit:)")
    sel_ap.add_argument("--verbose", action="store_true", help="List excluded files and why")
    sel_ap.set_defaults(func=cmd_select)

    # glyphs
    gl_ap = sub.add_parser("glyphs", help="Scan for or vendor the glyphs a set of sources needs (glyph registry)")
    gl_sub = gl_ap.add_subparsers(dest="glyphs_command")
    for name, help_text in (
        ("scan", "Report what the sources need that the coverage fonts and registry lack (exit 1 if anything)"),
        ("grow", "Vendor what the sources need into profiles/40_latex_import/assets/glyph_registry.json"),
    ):
        g = gl_sub.add_parser(name, help=help_text)
        g.add_argument("input", nargs="+", help="Markdown files or directories (searched recursively)")
        g.add_argument("--coverage-font", action="append", help="Font file the body is set in (default: fc-match 'DejaVu Sans')")
        g.add_argument("--noto-source", help="googlefonts/noto-emoji source tree (has svg/)")
        g.add_argument("--noto-version", default="v2.051", help="Recorded in the registry")
        g.add_argument("--cjk-font", help="Noto Sans CJK Regular .ttc/.otf to subset")
        g.add_argument("--cjk-font-bold", help="Noto Sans CJK Bold .ttc/.otf to subset")
        g.add_argument("--cjk-font-number", type=int, default=0, help="Face index in a .ttc (0 = JP)")
        g.add_argument("--cjk-source-label", default="notofonts/noto-cjk Sans 2.004 (JP face)")
        g.set_defaults(func=cmd_glyphs)

    args = ap.parse_args()
    if args.command is None:
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
