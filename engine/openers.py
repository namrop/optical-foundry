"""D4 — the chapter-opener contract, declared by a profile.

Promotion map D4 (contracts/CHAPTER_OPENERS_CONTRACT.md; Codex 0 5e71dd2, c67bba5,
cea2861). What Codex 0 decides about a chapter's opening — which paragraph gets a raised
capital, what it skips, what it never letters, how the capital is set — was written into
its template and its composition filter. Here it is an engine mechanism a profile
declares in its package (``profile.yaml``)::

    openers:
      capital: raised          # raised | none
      scale: 2.4               # capital size, times the body size (Codex 0: 2.4)
      font_command: headerfont # optional: a font switch the template defines
      color: LetterBody        # optional: an xcolor name
      small_caps: true         # the rest of the first word in small caps
      nudge: -0.05em           # kern between the capital and the word
      depth: 0.12em            # extra depth so line 2 clears a descender
      spill: {B: 0.323em}      # per-letter right kern for ink left of the origin
      epigraph_gap: 2.2em      # space between an opener's epigraph and the prose

Placement rules (Codex 0's, rulings of 2026-08-03; not optional, they are the contract):
the first prose paragraph after an opener gets the capital; leading raw markers (a rail
begin) are stepped over; an opening block quote (an epigraph) is skipped and the prose
beneath it lettered; a verse or heading opener gets no capital; a letter inside an
opening colour macro inherits its colour. Anything that does not begin with an ASCII
letter keeps a plain opening (fail-open).

A chapter opening always starts a new page; the bundle compiler already enforces that
for every source with a ``chapter_opener`` (2026-08-12 ruling), so it is not a setting.

Codex 0 keeps its own implementation (codex0_composition.lua, codex0.tex) until G2 moves
its profile out of the engine; this module is for every other profile.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

ENGINE = Path(__file__).resolve().parent
FILTER = ENGINE / "filters" / "of_openers.lua"
TEX = ENGINE / "latex" / "of_openers.tex"

_DIM_RE = re.compile(r"^-?(\d+(\.\d+)?|\.\d+)(em|ex|pt|in|mm|cm|bp)$")
_NAME_RE = re.compile(r"^[A-Za-z]+$")
_KEYS = {"capital", "scale", "font_command", "color", "small_caps", "nudge", "depth", "spill", "epigraph_gap"}


class OpenerError(ValueError):
    pass


@dataclass
class OpenerPlan:
    preamble: list[str]
    filter_path: Path = FILTER
    record: dict[str, Any] = field(default_factory=dict)


def _dim(name: str, value: Any) -> str:
    text = str(value).strip()
    if not _DIM_RE.match(text):
        raise OpenerError(f"openers.{name} must be a dimension like 0.12em, not {value!r}")
    return text


def plan_openers(spec: dict[str, Any] | None) -> OpenerPlan | None:
    """Validate a profile's opener declaration and lower it. None when it declares none."""
    if not spec:
        return None
    if not isinstance(spec, dict):
        raise OpenerError("openers must be a mapping")
    unknown = set(spec) - _KEYS
    if unknown:
        raise OpenerError(f"openers: unknown key(s) {sorted(unknown)}; known: {sorted(_KEYS)}")
    capital = str(spec.get("capital", "raised"))
    if capital not in ("raised", "none"):
        raise OpenerError("openers.capital must be raised or none")
    try:
        scale = float(spec.get("scale", 2.4))
    except (TypeError, ValueError):
        raise OpenerError("openers.scale must be a number") from None
    if not 1.0 <= scale <= 6.0:
        raise OpenerError("openers.scale must be between 1 and 6")
    font = spec.get("font_command")
    if font is not None and not _NAME_RE.match(str(font)):
        raise OpenerError("openers.font_command must be a command name (letters only)")
    color = spec.get("color")
    if color is not None and not _NAME_RE.match(str(color)):
        raise OpenerError("openers.color must be an xcolor name (letters only)")
    nudge = _dim("nudge", spec.get("nudge", "0em"))
    depth = _dim("depth", spec.get("depth", "0.12em"))
    spill = spec.get("spill") or {}
    if not isinstance(spill, dict):
        raise OpenerError("openers.spill must map letters to dimensions")
    lines = [f"\\input{{{TEX.as_posix()}}}",
             f"\\renewcommand{{\\OFOpenerCapitalScale}}{{{scale:g}}}",
             f"\\renewcommand{{\\OFOpenerCapitalNudge}}{{{nudge}}}",
             f"\\renewcommand{{\\OFOpenerCapitalDepth}}{{{depth}}}"]
    if font:
        lines.append(f"\\renewcommand{{\\OFOpenerCapitalFont}}{{\\{font}}}")
    if color:
        lines.append(f"\\renewcommand{{\\OFOpenerCapitalColor}}[1]{{\\textcolor{{{color}}}{{#1}}}}")
    if spec.get("small_caps", True) is False:
        lines.append("\\renewcommand{\\OFOpenerRestShape}[1]{#1}")
    for letter, value in sorted(spill.items()):
        if not (isinstance(letter, str) and len(letter) == 1 and letter.isascii() and letter.isalpha()):
            raise OpenerError(f"openers.spill: {letter!r} is not a letter")
        lines.append(f"\\OFOpenerSpill{{{letter.upper()}}}{{{_dim('spill.' + letter, value)}}}")
    if spec.get("epigraph_gap") is not None:
        # The engine's epigraph fallback (engine/template_contract.py) reads this hook.
        lines.append(f"\\providecommand{{\\CodexEpigraphToBodyGap}}{{\\vspace{{{_dim('epigraph_gap', spec['epigraph_gap'])}}}}}")
    record = {"capital": capital, "scale": scale, "font_command": font, "color": color,
              "spill_letters": len(spill), "epigraph_gap": spec.get("epigraph_gap")}
    return OpenerPlan(preamble=lines, record=record)


def filter_metadata(plan: OpenerPlan) -> str:
    return json.dumps({"capital": plan.record["capital"]}, separators=(",", ":"))
