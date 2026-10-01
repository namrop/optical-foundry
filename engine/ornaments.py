"""Ornament slots and register rails (promotion map D1, D2).

contracts/ORNAMENT_SLOTS_CONTRACT.md; keeper rulings 01a0f951-dc5d ("there are
many ornament slots that exist, they don't all need to be filled, but there are
rules about how each works. all of this comes with the profile") and
01a0f99a-b2db (marked by hand; profiles in their own repository; the
keeper-capture book fills breath, hinge and rails; Codex 0's rail numbers; a
profile "can tighten but not loosen").

The engine owns the slots and their rules. A profile package (engine/
profile_package.py) fills the ones it wants, in its `ornaments:` block::

    ornaments:
      rails:
        class: literal-voice      # the Div class that marks a block
        run_key: null             # optional attribute that separates runs (Codex 0: story)
        width: 0.50in             # the rail slot
        line_height: 0.18816in    # one line, for art checks (Codex 0: 7.15in / 38)
        min_lines: 4              # shortest page-local rail drawn
        ladder: {step: 2, max: 38}
        inner_share: 0.5
        art: [{path: rails/a.png, rung: 12}, ...]   # rung optional: the longest it fills
      slots:
        breath: {class: breath, height: 1.7em, gap: 1\\baselineskip, art: [breath/b1.png]}
        hinge:  {class: hinge, height: 2.9em, gap: 2\\baselineskip, art: []}

This module checks the declaration (slot names, tighten-only rules, art against
§2 of the contract) and produces what a render needs: preamble lines and the
filter's configuration.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENGINE_LATEX = Path(__file__).resolve().parent / "latex"
FILTER = Path(__file__).resolve().parent / "filters" / "of_ornaments.lua"

# The slots the page-position law governs, with the engine's rules (Codex 0's law).
# index is the band attribute value; it must stay stable.
BAND_SLOTS: dict[str, dict[str, Any]] = {
    "whisper":      {"index": 1, "top": "drop", "foot": "drop"},
    "breath":       {"index": 2, "top": "drop", "foot": "drop"},
    "hinge":        {"index": 3, "top": "drop", "foot": "drop"},
    "passage_rule": {"index": 4, "top": "drop", "foot": "drop"},
    "tailpiece":    {"index": 5, "top": "keep", "foot": "keep_first"},
    "threshold":    {"index": 6, "top": "keep", "foot": "keep_first"},
}
# Named in the contract, not yet placed by the engine: filling one is an error for now.
NOT_YET = ("edge_companion", "blank_leaf", "folio_chip", "divider_plate", "floating_plate",
           "image_initial", "title_background")
STRICTNESS = {"top": ["keep", "drop"], "foot": ["keep_first", "drop"]}

CODEX0_RAILS = {"width": "0.50in", "line_height": "0.18816in", "min_lines": 4,
                "ladder": {"step": 2, "max": 38}, "inner_share": 0.5}
MIN_DPI = 300

_DIM = re.compile(r"^(\d+(?:\.\d+)?)(in|pt|mm|cm)$")
_PER_INCH = {"in": 1.0, "pt": 1 / 72.27, "mm": 1 / 25.4, "cm": 1 / 2.54}


class OrnamentError(ValueError):
    pass


def inches(value: str) -> float:
    m = _DIM.match(str(value).strip())
    if not m:
        raise OrnamentError(f"not a plain dimension (in, pt, mm, cm): {value!r}")
    return float(m.group(1)) * _PER_INCH[m.group(2)]


@dataclass
class ArtCheck:
    path: Path
    errors: list[str] = field(default_factory=list)
    aspect: float | None = None
    rung: int | None = None


def check_art(path: Path, *, placed_height_in: float | None = None,
              placed_width_in: float | None = None) -> ArtCheck:
    """§2.1: transparent background, contained (no ink on any border row or
    column), at least 300 dpi at the placed size. Returns the ink aspect."""
    from PIL import Image

    result = ArtCheck(path)
    if not path.is_file():
        result.errors.append("missing")
        return result
    with Image.open(path) as im:
        if "A" not in im.getbands():
            result.errors.append("no alpha channel")
            return result
        alpha = im.getchannel("A")
        w, h = alpha.size
        edges = [alpha.crop((0, 0, w, 1)), alpha.crop((0, h - 1, w, h)),
                 alpha.crop((0, 0, 1, h)), alpha.crop((w - 1, 0, w, h))]
        if any(edge.getextrema()[1] > 0 for edge in edges):
            result.errors.append("not contained: ink touches the canvas border")
        bbox = alpha.getbbox()
        if not bbox:
            result.errors.append("no ink")
            return result
        ink_w, ink_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    result.aspect = ink_h / ink_w
    if placed_height_in and ink_h / placed_height_in < MIN_DPI:
        result.errors.append(f"{ink_h / placed_height_in:.0f} dpi at the placed height (< {MIN_DPI})")
    if placed_width_in and ink_w / placed_width_in < MIN_DPI:
        result.errors.append(f"{ink_w / placed_width_in:.0f} dpi at the placed width (< {MIN_DPI})")
    return result


@dataclass
class OrnamentPlan:
    """What a render needs for one profile's ornaments."""
    preamble: list[str]
    filter_path: Path
    filter_config: dict[str, Any]
    record: dict[str, Any]


def _tightened(slot: str, rule: str, value: str | None) -> str:
    default = BAND_SLOTS[slot][rule]
    if value is None:
        return default
    order = STRICTNESS[rule]
    if value not in order:
        raise OrnamentError(f"{slot}.{rule}: {value!r} is not one of {order}")
    if order.index(value) < order.index(default):
        raise OrnamentError(
            f"{slot}.{rule}: {value!r} would loosen the engine's {default!r}; a profile may tighten a rule, never loosen it"
        )
    return value


def plan_ornaments(ornaments: dict[str, Any] | None, package_dir: Path) -> OrnamentPlan | None:
    """Validate a profile's ornament declaration and lower it. None when it fills nothing."""
    if not ornaments:
        return None
    errors: list[str] = []
    preamble = [
        f'\\directlua{{dofile("{ENGINE_LATEX / "of_ornament_law.lua"}")}}',
        f"\\input{{{ENGINE_LATEX / 'of_ornaments.tex'}}}",
    ]
    filter_config: dict[str, Any] = {"rail": None, "slots": {}}
    record: dict[str, Any] = {"slots": {}, "rails": None}
    law: dict[str, dict[str, str]] = {}

    slots = ornaments.get("slots") or {}
    for name, spec in slots.items():
        spec = spec or {}
        if name in NOT_YET:
            errors.append(f"slot {name!r} is in the contract but not yet placed by the engine")
            continue
        if name not in BAND_SLOTS:
            errors.append(f"unknown slot {name!r}; known: {sorted(BAND_SLOTS)} and rails")
            continue
        try:
            top = _tightened(name, "top", spec.get("top"))
            foot = _tightened(name, "foot", spec.get("foot"))
        except OrnamentError as exc:
            errors.append(str(exc))
            continue
        index = BAND_SLOTS[name]["index"]
        law[str(index)] = {"name": name, "top": top, "foot": foot}
        height, gap = str(spec.get("height", "1.7em")), str(spec.get("gap", "1\\baselineskip"))
        preamble.append(f"\\OFOrnamentDefine{{{name}}}{{{index}}}{{{height}}}{{{gap}}}")
        art_ok = []
        for item in spec.get("art") or []:
            path = (package_dir / (item["path"] if isinstance(item, dict) else item)).resolve()
            check = check_art(path)
            if check.errors:
                errors.append(f"{name} art {path.name}: {'; '.join(check.errors)}")
                continue
            art_ok.append(path)
            preamble.append(f"\\OFOrnamentArtAdd{{{name}}}{{{path}}}")
        filter_config["slots"][name] = {"class": spec.get("class", name), "index": index}
        record["slots"][name] = {"class": spec.get("class", name), "top": top, "foot": foot,
                                 "art": len(art_ok)}

    rails = ornaments.get("rails")
    if rails:
        cfg = {**CODEX0_RAILS, **rails}
        ladder = {**CODEX0_RAILS["ladder"], **(rails.get("ladder") or {})}
        try:
            width_in, line_in = inches(cfg["width"]), inches(cfg["line_height"])
        except OrnamentError as exc:
            errors.append(f"rails: {exc}")
            width_in = line_in = 0.0
        step, top_rung = int(ladder["step"]), int(ladder["max"])
        rungs = list(range(step, top_rung + 1, step))
        preamble += [
            f"\\OFRailSetWidth{{{cfg['width']}}}",
            f"\\OFRailSetMinLines{{{int(cfg['min_lines'])}}}",
            f"\\OFRailSetLadder{{{step}}}{{{top_rung}}}",
            f"\\renewcommand{{\\OFRailInnerShare}}{{{cfg['inner_share']}}}",
        ]
        pool: dict[int, int] = {}
        for item in cfg.get("art") or []:
            item = item if isinstance(item, dict) else {"path": item}
            path = (package_dir / item["path"]).resolve()
            probe = check_art(path)
            if probe.errors:
                errors.append(f"rail art {path.name}: {'; '.join(probe.errors)}")
                continue
            # Aspect decides the rung: a piece fills L lines only if
            # aspect >= L * line height / slot width.
            fills = [L for L in rungs if width_in and probe.aspect >= L * line_in / width_in]
            if not fills:
                errors.append(f"rail art {path.name}: aspect {probe.aspect:.2f} fills no rung")
                continue
            rung = int(item.get("rung") or fills[-1])
            if rung not in fills:
                errors.append(f"rail art {path.name}: aspect {probe.aspect:.2f} cannot fill rung {rung}")
                continue
            placed = check_art(path, placed_height_in=rung * line_in)
            if placed.errors:
                errors.append(f"rail art {path.name}: {'; '.join(placed.errors)}")
                continue
            pool[rung] = pool.get(rung, 0) + 1
            preamble.append(f"\\OFRailPoolAdd{{{rung}}}{{{path}}}")
        filter_config["rail"] = {"class": cfg.get("class", "rail"), "run_key": cfg.get("run_key")}
        record["rails"] = {"class": cfg.get("class", "rail"), "run_key": cfg.get("run_key"),
                           "width": cfg["width"], "min_lines": int(cfg["min_lines"]),
                           "ladder": {"step": step, "max": top_rung},
                           "pieces_by_rung": {str(k): pool[k] for k in sorted(pool)},
                           "empty_rungs": [L for L in rungs if L not in pool]}

    if errors:
        raise OrnamentError("profile ornaments: " + "; ".join(errors))
    preamble.append(f"\\directlua{{of_ornament_law.configure({_lua_table(law)})}}")
    record["law"] = law
    return OrnamentPlan(preamble=preamble, filter_path=FILTER, filter_config=filter_config, record=record)


def _lua_table(law: dict[str, dict[str, str]]) -> str:
    parts = []
    for index, rule in sorted(law.items(), key=lambda kv: int(kv[0])):
        parts.append(f'[{index}]={{name="{rule["name"]}",top="{rule["top"]}",foot="{rule["foot"]}"}}')
    return "{" + ",".join(parts) + "}"


def filter_metadata(plan: OrnamentPlan) -> str:
    return json.dumps(plan.filter_config, separators=(",", ":"))
