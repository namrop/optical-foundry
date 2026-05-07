"""Manifest compiler base and concrete compilers.

A ManifestCompiler validates a typed render manifest and produces a
ProjectionPlan. Each supported (kind, schema_version) pair should have one
dedicated compiler registered through the ManifestRegistry.

Concrete compilers:
  - CompositeBundleCompiler: composite_bundle / bundle_manifest_v1
  - LabelRunCompiler:          label_run / label_run_v1
  - StickerSheetCompiler:      sticker_sheet / sticker_sheet_v1
  - ForgePacketReviewCompiler: forge_packet_review / packet_review_manifest_v1
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from engine.render_planner import RenderPlan, plan_manifest_render
from engine.projection_plan import AssemblyView, ProjectionPlan


class ManifestCompiler(ABC):
    """Base for all manifest compilers.

    Subclasses must define `compile` and `validate`.
    """

    kind: str = ""
    schema_version: str = ""

    @abstractmethod
    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        """Validate the manifest and produce a ProjectionPlan."""

    @abstractmethod
    def validate(self, manifest: dict[str, Any]) -> list[str]:
        """Return a list of validation errors (empty = valid)."""


class NullCompiler(ManifestCompiler):
    """Identity compiler used when the input is a plain Markdown document.

    This compiler exists so the render dispatch can treat Markdown documents
    as a degenerate manifest case without special-casing the dispatch path.
    """

    kind = "_document"
    schema_version = "_document_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        raise NotImplementedError("NullCompiler is a bypass marker, not an executable compiler")

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        return []


# Module-level singleton for the identity bypass.
null_compiler = NullCompiler()


# ──────────────────────────────────────────────
#  Helpers shared across compilers
# ──────────────────────────────────────────────


def _sha256_hex(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _split_frontmatter_and_body(text: str) -> tuple[dict[str, Any] | None, str]:
    """Split YAML frontmatter from Markdown body.

    Returns (parsed_dict_or_None, body_str). Returns (None, text) if no
    frontmatter is detected or parsing fails.
    """
    try:
        import yaml
    except ImportError:
        return None, text

    text = text.lstrip()
    if not text.startswith("---"):
        return None, text

    idx = text.find("---", 3)
    if idx == -1:
        return None, text

    fm_block = text[3:idx].strip()
    body = text[idx + 3 :]

    try:
        fm = yaml.safe_load(fm_block)
    except yaml.YAMLError:
        return None, text

    return fm if isinstance(fm, dict) else None, body


def _demote_headings(body: str, levels: int = 2) -> str:
    """Demote all ATX headings by `levels` to prevent source headings from
    competing with the assembly-level section heading."""
    import re

    def _demote(m: re.Match) -> str:
        hashes = m.group(1)
        if len(hashes) + levels > 6:
            return "######" + m.group(2)
        return ("#" * (len(hashes) + levels)) + m.group(2)

    return re.sub(r"^(#{1,6})( .*)$", _demote, body, flags=re.MULTILINE)


def _write_temp_markdown(prefix: str, content: str) -> Path:
    """Write assembled Markdown to a named temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".md", prefix=f"of_{prefix}_")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return Path(path)


def _apply_manifest_resolution(manifest: dict[str, Any], assembly: AssemblyView) -> tuple[RenderPlan, dict[str, dict[str, Any]]]:
    """Populate assembly-family fields and return child profile evidence by object id."""

    render_plan = plan_manifest_render(manifest)
    resolved = render_plan.manifest
    if resolved is None:
        return render_plan, {}

    assembly.manifest_family = resolved.manifest_family
    assembly.manifest_subtype = resolved.manifest_subtype
    assembly.assembly_strategy = resolved.assembly_strategy
    assembly.numbering_strategy = resolved.numbering_strategy

    child_profiles: list[dict[str, Any]] = []
    for child in render_plan.children:
        evidence = {
            "object_id": child.object_id,
            "source_path": str(child.source_path) if child.source_path else "",
            "role": child.role,
            "order": child.order,
            "requested_profile_id": child.requested_profile_id,
            "requested_profile_family": child.requested_profile_family,
            "resolved_profile_id": child.resolved_profile.canonical_profile_id,
            "resolved_profile_request_id": child.resolved_profile.profile_id,
            "profile_family": child.resolved_profile.profile_family,
            "defaults_stack": [path.name for path in child.resolved_profile.defaults_stack],
            "template": child.resolved_profile.template_path.name,
        }
        child_profiles.append(evidence)

    assembly.child_profiles = child_profiles
    return render_plan, {entry["object_id"]: entry for entry in child_profiles}


def _manifest_boundary_assertions(render_plan: RenderPlan) -> dict[str, Any]:
    resolved = render_plan.manifest
    assembly = render_plan.assembly
    if resolved is None or assembly is None:
        return {}
    return {
        "manifest_family": resolved.manifest_family,
        "manifest_subtype": resolved.manifest_subtype,
        "assembly_strategy": assembly.strategy,
        "numbering_strategy": assembly.numbering_strategy,
        **resolved.boundary,
    }


def _inventory_profile_fields(child_profile_by_id: dict[str, dict[str, Any]], uid: str) -> dict[str, Any]:
    child = child_profile_by_id.get(uid)
    if child is None:
        return {}
    return {
        "requested_profile_id": child.get("requested_profile_id"),
        "requested_profile_family": child.get("requested_profile_family"),
        "resolved_profile_id": child.get("resolved_profile_id"),
        "profile_family": child.get("profile_family"),
    }


# ──────────────────────────────────────────────
#  Concrete manifest compilers
# ──────────────────────────────────────────────


class CompositeBundleCompiler(ManifestCompiler):
    """Compile a composite_bundle / bundle_manifest_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    containing a title page, reader guide, TOC, ordered source sections (with
    frontmatter blocks), figures, afterword, and provenance block.
    """

    kind = "composite_bundle"
    schema_version = "bundle_manifest_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        bundle_id = manifest["bundle_id"]
        profile = manifest["profile"]
        pres = manifest.get("presentation", {})
        title = pres.get("title", manifest.get("bundle_name", bundle_id))
        subtitle = pres.get("subtitle", "")
        authors = pres.get("authors", [])
        date = pres.get("date", "")

        render_cfg = manifest.get("render", {})
        gen_cfg = manifest.get("generated", {})

        sources = manifest.get("sources", [])
        figures = manifest.get("figures", [])

        # --- build assembly view ---
        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=title,
            assembly_subtitle=subtitle,
            source_order=[],
            source_paths={},
            source_roles={},
            source_digests={},
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        # --- assemble intermediate Markdown ---
        lines: list[str] = []

        # Title metadata is passed through Pandoc --metadata; the template
        # renders the title page from metadata. We add a brief preamble.
        abstract = pres.get("abstract", "")
        if abstract:
            lines.append(f"> {abstract}")
            lines.append("")

        # TOC is handled by PandocRenderer's --toc flag via ProjectionPlan.toc.
        # Do not emit \tableofcontents here (would duplicate pandoc --toc).

        # reader guide
        rg = gen_cfg.get("reader_guide", {})
        if rg.get("enabled", False):
            rg_title = rg.get("title", "Reader Guide")
            lines.append("\\newpage")
            lines.append(f"# {rg_title}")
            for section_line in rg.get("sections", []):
                lines.append(section_line)
                lines.append("")

        # source sections
        source_order_uid = []
        for src in sorted(sources, key=lambda s: s.get("order", 99)):
            uid = src["uid"]
            src_path = Path(src["path"])
            src_role = src.get("role", "primary_anchor")
            src_title = src.get("title", uid)
            inc_fm = src.get("include_frontmatter", "full")
            suppress_fm = src.get("suppress_frontmatter", False)

            assembly.source_order.append(uid)
            assembly.source_paths[uid] = str(src_path)
            assembly.source_roles[uid] = src_role

            if not src_path.exists():
                continue

            assembly.source_digests[uid] = _sha256_hex(src_path)

            raw_text = src_path.read_text()
            fm, body = _split_frontmatter_and_body(raw_text)

            lines.append("\\newpage")
            lines.append(f"# {src_title}")

            # frontmatter block
            if not suppress_fm and inc_fm == "full" and fm:
                try:
                    import yaml as _yaml
                    fm_yaml = _yaml.dump(fm, default_flow_style=False, allow_unicode=True)
                except ImportError:
                    fm_yaml = str(fm)
                lines.append("\\textbf{Source Frontmatter}")
                lines.append("")
                lines.append("```yaml")
                lines.append(fm_yaml.rstrip())
                lines.append("```")
                lines.append("")
            elif not suppress_fm and inc_fm == "summary" and fm:
                lines.append("\\textbf{Source Frontmatter (summary)}")
                lines.append("")
                for k, v in sorted(fm.items()):
                    if isinstance(v, (list, dict)):
                        continue
                    lines.append(f"- **{k}**: {v}")
                lines.append("")

            # source body with demoted headings
            demoted = _demote_headings(body)
            lines.append(demoted.rstrip())
            lines.append("")

            # figures placed after this source
            src_order = src.get("order", 0)
            for fig in figures:
                if fig.get("after_source_order", -1) == src_order:
                    fig_path = fig.get("path", "")
                    caption = fig.get("caption", "")
                    placement = fig.get("placement", "dedicated_page")
                    if placement == "dedicated_page":
                        lines.append(f"\\newpage")
                    lines.append(f"![]({fig_path})" if not caption else f"![]({fig_path}){{{{width=80%}}}}")
                    if caption:
                        lines.append(f"\\textit{{{caption}}}")
                    lines.append("")

        # afterword
        aw = gen_cfg.get("afterword", {})
        if aw.get("enabled", False):
            aw_title = aw.get("title", "Afterword")
            aw_content = aw.get("content", "")
            lines.append("\\newpage")
            lines.append(f"# {aw_title}")
            if aw_content:
                lines.append(aw_content)
            lines.append("")

        # provenance block
        lines.append("\\newpage")
        lines.append("# Provenance & Evidence")
        lines.append("\\textbf{Source Inventory}")
        lines.append("")
        for uid in assembly.source_order:
            path = assembly.source_paths.get(uid, "")
            role = assembly.source_roles.get(uid, "")
            digest = assembly.source_digests.get(uid, "(missing)")
            lines.append(f"- **{uid}** ({role}): `{path}` [sha256: `{digest[:16]}...`]")
        if figures:
            lines.append("")
            lines.append("\\textbf{Figure Inventory}")
            lines.append("")
            for fig in figures:
                lines.append(f"- {fig.get('caption', fig.get('path', 'unknown'))}: `{fig.get('path', '?')}`")

        assembled_content = "\n".join(lines)
        render_source = _write_temp_markdown(f"bundle_{bundle_id}", assembled_content)

        # --- build ProjectionPlan ---
        plan = ProjectionPlan(
            profile_id=profile,
            render_id=bundle_id,
            render_source=render_source,
            title=title,
            subtitle=subtitle,
            author=", ".join(authors),
            date=date,
            toc=render_cfg.get("include_toc", True),
            toc_depth=render_cfg.get("toc_depth", 3),
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "path": assembly.source_paths.get(uid),
                    "role": assembly.source_roles.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            figure_inventory=[
                {"path": f.get("path"), "caption": f.get("caption"), "placement": f.get("placement")}
                for f in figures
            ],
            boundary_assertions=_manifest_boundary_assertions(render_plan),
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        # envelope
        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("bundle_id"):
            errors.append("missing bundle_id")

        if not manifest.get("profile"):
            errors.append("missing profile")

        # sources
        sources = manifest.get("sources")
        if not sources or not isinstance(sources, list):
            errors.append("sources must be a non-empty list")
        else:
            seen_uids = set()
            seen_orders = set()
            for i, src in enumerate(sources):
                uid = src.get("uid")
                if not uid:
                    errors.append(f"source[{i}] missing uid")
                elif uid in seen_uids:
                    errors.append(f"duplicate uid: {uid}")
                else:
                    seen_uids.add(uid)

                order = src.get("order")
                if order is None or not isinstance(order, int) or order < 1:
                    errors.append(f"source[{i}] missing or invalid order")
                elif order in seen_orders:
                    errors.append(f"duplicate order: {order}")
                else:
                    seen_orders.add(order)

                path = src.get("path")
                if not path:
                    errors.append(f"source[{i}] missing path")
                elif not Path(path).exists():
                    errors.append(f"source[{i}] path not found: {path}")

                role = src.get("role")
                if role not in {"primary_anchor", "supporting_anchor", "appendix", "reference"}:
                    errors.append(f"source[{i}] unknown role: {role}")

        # figures
        figures = manifest.get("figures", [])
        if isinstance(figures, list):
            for i, fig in enumerate(figures):
                if not fig.get("path"):
                    errors.append(f"figure[{i}] missing path")

        return errors


class LabelRunCompiler(ManifestCompiler):
    """Compile a label_run / label_run_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    with slot-ordered label content, each drawn from its label source file.
    """

    kind = "label_run"
    schema_version = "label_run_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        run_id = manifest["run_id"]
        profile = manifest["profile"]
        sheet_spec = manifest.get("sheet_spec", "")
        output_name = manifest.get("output_name", run_id)
        labels = manifest.get("labels", [])

        # build assembly view
        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=f"Label Run: {run_id}",
            assembly_subtitle=f"Sheet spec: {sheet_spec}",
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        # assemble intermediate Markdown — one section per slot
        lines: list[str] = []
        lines.append(f"# Label Run: {run_id}")
        lines.append(f"**Sheet spec:** {sheet_spec}  ")
        lines.append(f"**Profile:** {profile}  ")
        lines.append(f"**Labels:** {len(labels)}  ")
        lines.append("")

        for lbl in sorted(labels, key=lambda l: l.get("slot", 9999)):
            slot = lbl["slot"]
            src_path = Path(lbl["source"])
            uid = f"slot-{slot}"

            assembly.source_order.append(uid)
            assembly.source_paths[uid] = str(src_path)
            assembly.source_roles[uid] = "label"

            lines.append(f"\\newpage\\section{{Slot {slot}}}")

            if src_path.exists():
                assembly.source_digests[uid] = _sha256_hex(src_path)
                raw_text = src_path.read_text()
                fm, body = _split_frontmatter_and_body(raw_text)

                if fm:
                    try:
                        import yaml as _yaml
                        fm_yaml = _yaml.dump(fm, default_flow_style=False, allow_unicode=True)
                    except ImportError:
                        fm_yaml = str(fm)
                    lines.append("```yaml")
                    lines.append(fm_yaml.rstrip())
                    lines.append("```")
                    lines.append("")

                lines.append(body.rstrip())
            else:
                lines.append(f"*[Label source not found: {src_path}]*")

            lines.append("")

        assembled_content = "\n".join(lines)
        render_source = _write_temp_markdown(f"label_{run_id}", assembled_content)

        plan = ProjectionPlan(
            profile_id=profile,
            render_id=run_id,
            render_source=render_source,
            title=output_name,
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "slot": int(uid.split("-")[1]) if uid.startswith("slot-") else 0,
                    "path": assembly.source_paths.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            boundary_assertions={
                **_manifest_boundary_assertions(render_plan),
                "layout_mode": "content_driven_placeholder",
                "grid_validated": False,
                "warnings": [
                    "Label run currently renders slot-ordered content as a synthetic placeholder document.",
                    "Physical Avery/grid placement remains content-driven and is not validated by this compiler.",
                ],
            },
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("run_id"):
            errors.append("missing run_id")

        if not manifest.get("sheet_spec"):
            errors.append("missing sheet_spec")

        labels = manifest.get("labels")
        if not labels or not isinstance(labels, list):
            errors.append("labels must be a non-empty list")
        else:
            seen_slots = set()
            for i, lbl in enumerate(labels):
                slot = lbl.get("slot")
                if slot is None or not isinstance(slot, int) or slot < 1:
                    errors.append(f"label[{i}] missing or invalid slot")
                elif slot in seen_slots:
                    errors.append(f"label[{i}] duplicate slot: {slot}")
                else:
                    seen_slots.add(slot)

                src = lbl.get("source")
                if not src:
                    errors.append(f"label[{i}] missing source")
                elif not Path(src).exists():
                    errors.append(f"label[{i}] source not found: {src}")

        return errors


class StickerSheetCompiler(ManifestCompiler):
    """Compile a sticker_sheet / sticker_sheet_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    with cell-ordered sticker content.
    """

    kind = "sticker_sheet"
    schema_version = "sticker_sheet_v1"

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        sheet_id = manifest["sheet_id"]
        profile = manifest["profile"]
        layout = manifest.get("layout", {})
        grid = layout.get("grid", [1, 1])
        cell_size = layout.get("cell_size", [2.5, 2.5])
        show_cut = layout.get("show_cut_lines", True)
        cells = manifest.get("cells", [])

        max_row, max_col = grid[0] if len(grid) >= 1 else 1, grid[1] if len(grid) >= 2 else 1

        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=f"Sticker Sheet: {sheet_id}",
            assembly_subtitle=f"Grid: {max_row}×{max_col}",
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        lines: list[str] = []
        lines.append(f"# Sticker Sheet: {sheet_id}")
        lines.append(f"**Grid:** {max_row}×{max_col}  ")
        lines.append(f"**Cell size:** {cell_size[0] if cell_size else '?'}in × {cell_size[1] if len(cell_size)>1 else '?'}in  ")
        lines.append(f"**Cut lines:** {'on' if show_cut else 'off'}  ")
        lines.append(f"**Cells:** {len(cells)}  ")
        lines.append("")

        for cell in cells:
            pos = cell.get("position", [0, 0])
            row, col = pos[0] if len(pos) >= 1 else 0, pos[1] if len(pos) >= 2 else 0
            uid = f"cell-{row}-{col}"
            content = cell.get("content", "")
            source = cell.get("source")
            image = cell.get("image")

            assembly.source_order.append(uid)
            assembly.source_roles[uid] = "sticker"

            lines.append(f"\\newpage\\section{{Cell [{row},{col}]}}")

            if source:
                src_path = Path(source)
                assembly.source_paths[uid] = str(src_path)
                if src_path.exists():
                    assembly.source_digests[uid] = _sha256_hex(src_path)
                    lines.append(src_path.read_text().rstrip())
                else:
                    lines.append(f"*[Source not found: {source}]*")
            elif content:
                assembly.source_paths[uid] = f"inline://{uid}"
                assembly.source_digests[uid] = hashlib.sha256(content.encode()).hexdigest()
                lines.append(content)

            if image:
                img_path = image
                lines.append(f"![]({img_path})")

            lines.append("")

        assembled_content = "\n".join(lines)
        render_source = _write_temp_markdown(f"sticker_{sheet_id}", assembled_content)

        plan = ProjectionPlan(
            profile_id=profile,
            render_id=sheet_id,
            render_source=render_source,
            title=sheet_id,
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "path": assembly.source_paths.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            boundary_assertions={
                **_manifest_boundary_assertions(render_plan),
                "layout_mode": "content_driven_placeholder",
                "grid_validated": False,
                "warnings": [
                    "Sticker sheet currently renders cell-ordered content as a synthetic placeholder document.",
                    "Physical sticker grid placement remains content-driven and is not validated by this compiler.",
                ],
            },
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("sheet_id"):
            errors.append("missing sheet_id")

        if not manifest.get("profile"):
            errors.append("missing profile")

        layout = manifest.get("layout", {})
        grid = layout.get("grid", [])
        if not isinstance(grid, list) or len(grid) < 2 or not all(isinstance(g, int) and g > 0 for g in grid):
            errors.append("layout.grid must be a list of 2 positive integers")

        cells = manifest.get("cells")
        if not cells or not isinstance(cells, list):
            errors.append("cells must be a non-empty list")
        else:
            max_row = grid[0] if len(grid) >= 1 else 0
            max_col = grid[1] if len(grid) >= 2 else 0
            seen_positions = set()
            for i, cell in enumerate(cells):
                pos = cell.get("position")
                if not pos or not isinstance(pos, list) or len(pos) < 2:
                    errors.append(f"cell[{i}] missing or invalid position")
                else:
                    row, col = pos[0], pos[1]
                    if not (0 <= row < max_row and 0 <= col < max_col):
                        errors.append(f"cell[{i}] position [{row},{col}] out of grid bounds {max_row}×{max_col}")
                    pkey = (row, col)
                    if pkey in seen_positions:
                        errors.append(f"cell[{i}] duplicate position [{row},{col}]")
                    seen_positions.add(pkey)

                if not cell.get("content") and not cell.get("source") and not cell.get("image"):
                    errors.append(f"cell[{i}] has no content, source, or image")

        return errors


class ForgePacketReviewCompiler(ManifestCompiler):
    """Compile a forge_packet_review / packet_review_manifest_v1 manifest.

    Produces a ProjectionPlan whose render_source is an assembled Markdown file
    that projects packet lifecycle state for review: goal, constraints, plan,
    state, progress, validation, and questions.
    """

    kind = "forge_packet_review"
    schema_version = "packet_review_manifest_v1"

    DEFAULT_INCLUDE = [
        "GOAL.md",
        "CONSTRAINTS.md",
        "PLAN.md",
        "STATE.json",
        "PROGRESS.md",
        "VALIDATION.md",
    ]

    def compile(self, manifest: dict[str, Any], **kwargs: Any) -> ProjectionPlan:
        errors = self.validate(manifest)
        if errors:
            raise ValueError(f"manifest validation failed: {'; '.join(errors)}")

        profile = manifest["profile"]
        pkt = manifest.get("packet", {})
        pkt_path = Path(pkt.get("path", ""))
        includes = pkt.get("include", self.DEFAULT_INCLUDE)
        exclude_gen = pkt.get("exclude_generated", True)
        render_cfg = manifest.get("render", {})

        assembly = AssemblyView(
            assembly_kind=self.kind,
            schema_version=self.schema_version,
            assembly_title=f"Packet Review: {pkt_path.name if pkt_path else 'unknown'}",
            assembly_subtitle=str(pkt_path),
        )
        render_plan, child_profile_by_id = _apply_manifest_resolution(manifest, assembly)

        lines: list[str] = []
        lines.append(f"# Packet Review: {pkt_path.name if pkt_path else 'Packet State'}")
        lines.append(f"**Packet path:** `{pkt_path}`")
        lines.append(f"**Generated:** import time (placeholder)")
        lines.append("")

        # Include each file in the include list
        for inc_name in includes:
            inc_path = pkt_path / inc_name
            uid = inc_name.replace(".", "_")
            assembly.source_order.append(uid)
            assembly.source_paths[uid] = str(inc_path)
            assembly.source_roles[uid] = "packet_surface"

            if not inc_path.exists():
                lines.append("\\newpage")
                lines.append(f"# `{inc_name}`")
                lines.append(f"*[File not found: {inc_path}]*")
                lines.append("")
                continue

            assembly.source_digests[uid] = _sha256_hex(inc_path)
            lines.append("\\newpage")
            lines.append(f"# `{inc_name}`")

            if inc_path.suffix == ".json":
                import json
                try:
                    data = json.loads(inc_path.read_text())
                    if isinstance(data, dict):
                        lines.append("**JSON summary**")
                        lines.append("")
                        for k, v in data.items():
                            if isinstance(v, (str, int, float, bool)) or v is None:
                                lines.append(f"- **{k}**: {v}")
                            elif isinstance(v, list):
                                lines.append(f"- **{k}**: list[{len(v)}]")
                            elif isinstance(v, dict):
                                lines.append(f"- **{k}**: object[{len(v)} keys]")
                        lines.append("")
                    else:
                        lines.append(f"*JSON value of type {type(data).__name__}*\n")
                except json.JSONDecodeError:
                    lines.append("*Invalid JSON; raw content omitted from packet-review fixture render.*")
            else:
                lines.append(inc_path.read_text())
            lines.append("")

        # optionally include questions
        if render_cfg.get("include_questions", True):
            q_path = pkt_path / "QUESTIONS.md"
            if q_path.exists():
                uid = "QUESTIONS_md"
                assembly.source_order.append(uid)
                assembly.source_paths[uid] = str(q_path)
                assembly.source_roles[uid] = "packet_surface"
                assembly.source_digests[uid] = _sha256_hex(q_path)
                lines.append("\\newpage")
                lines.append("# `QUESTIONS.md`")
                lines.append(q_path.read_text())
                lines.append("")

        # optionally include dirty state summary
        if render_cfg.get("include_dirty_state_summary", True):
            ds_path = pkt_path / "DIRTY_STATE.json"
            if ds_path.exists():
                import json
                uid = "DIRTY_STATE_json"
                assembly.source_order.append(uid)
                assembly.source_paths[uid] = str(ds_path)
                assembly.source_roles[uid] = "packet_surface"
                assembly.source_digests[uid] = _sha256_hex(ds_path)
                lines.append("\\newpage")
                lines.append("# `DIRTY_STATE.json`")
                data = json.loads(ds_path.read_text())
                lines.append("**JSON summary**")
                lines.append("")
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, (str, int, float, bool)) or v is None:
                            lines.append(f"- **{k}**: {v}")
                        elif isinstance(v, list):
                            lines.append(f"- **{k}**: list[{len(v)}]")
                        elif isinstance(v, dict):
                            lines.append(f"- **{k}**: object[{len(v)} keys]")
                lines.append("")

        assembled_content = "\n".join(lines)
        render_source = _write_temp_markdown(f"pkt_review_{pkt_path.name if pkt_path else 'unknown'}", assembled_content)

        plan = ProjectionPlan(
            profile_id=profile,
            render_id=f"review-{pkt_path.name}" if pkt_path else "review-unknown",
            render_source=render_source,
            title=f"Packet Review: {pkt_path.name}" if pkt_path else "Packet Review",
            assembly=assembly,
            source_inventory=[
                {
                    "uid": uid,
                    "path": assembly.source_paths.get(uid),
                    "digest_sha256": assembly.source_digests.get(uid),
                    **_inventory_profile_fields(child_profile_by_id, uid),
                }
                for uid in assembly.source_order
            ],
            boundary_assertions={
                **_manifest_boundary_assertions(render_plan),
                "projection_mode": "packet_review",
                "packet_review_fixture": True,
                "include_questions": render_cfg.get("include_questions", True),
                "include_dirty_state_summary": render_cfg.get("include_dirty_state_summary", True),
            },
        )
        return plan

    def validate(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []

        if not isinstance(manifest, dict):
            return ["manifest is not a dict"]

        kind = manifest.get("kind")
        if kind != self.kind:
            errors.append(f"expected kind={self.kind}, got {kind}")
        sv = manifest.get("schema_version")
        if sv != self.schema_version:
            errors.append(f"expected schema_version={self.schema_version}, got {sv}")

        if not manifest.get("profile"):
            errors.append("missing profile")

        pkt = manifest.get("packet")
        if not pkt or not isinstance(pkt, dict):
            errors.append("packet must be a dict")
        else:
            pkt_path = pkt.get("path")
            if not pkt_path:
                errors.append("packet.path is required")
            elif not Path(pkt_path).is_dir():
                errors.append(f"packet.path is not a directory: {pkt_path}")

        return errors
