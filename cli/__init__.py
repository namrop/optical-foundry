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
    LabelRunCompiler,
    StickerSheetCompiler,
    ForgePacketReviewCompiler,
)
from renderers.pandoc_renderer import PandocRenderer
from renderers.document_renderer import DocumentRenderer
from engine.profile_checker import check_all_profiles, check_all_profiles_json, check_profile


def _default_registry() -> ManifestRegistry:
    reg = ManifestRegistry()
    for cls in [CompositeBundleCompiler, LabelRunCompiler, StickerSheetCompiler, ForgePacketReviewCompiler]:
        reg.register(cls.kind, cls.schema_version, cls)
    return reg


def cmd_doc(args: argparse.Namespace) -> int:
    dr = DocumentRenderer()
    evidence = dr.render(Path(args.input), args.profile, output_dir=args.output)
    print(json.dumps({"status": "ok", "render_id": evidence.get("render_id", "?"),
                       "output": evidence.get("output", {}).get("pdf_path", "unknown"),
                       "pages": evidence.get("output", {}).get("pdf_pages", 0)}, indent=2))
    return 0 if evidence.get("status") != "error" else 1


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

    plan = compiler.compile(raw)
    renderer = PandocRenderer()
    evidence = renderer.render(plan, output_dir=args.output)
    success = evidence.get("status") != "error"
    print(json.dumps({"status": "ok" if success else "error",
                       "render_id": evidence.get("render_id", "?"),
                       "output": evidence.get("output", {}).get("pdf_path", "unknown"),
                       "pages": evidence.get("output", {}).get("pdf_pages", 0)}, indent=2))
    return 0 if success else 1


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
    print(f"  Uses 40_latex ref: {cap.uses_40_latex}")
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
    mf_ap.set_defaults(func=cmd_manifest)

    # profiles
    pf_ap = sub.add_parser("profiles", help="Check profile capabilities and bundle compatibility")
    pf_ap.add_argument("--json", action="store_true", help="Output full JSON report")
    pf_ap.add_argument("--profile", help="Check a single profile")
    pf_ap.set_defaults(func=cmd_profiles)

    args = ap.parse_args()
    if args.command is None:
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
