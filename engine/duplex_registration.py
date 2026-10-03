"""E4 — a duplex registration instrument and its readings.

Promoted from Codex 0 (``tooling/duplex_registration_instrument.tex`` and the calibration
recorded in its status tracker: +1.801 mm, sd 0.008, over 17 patches). A printer does not
lay a sheet's back exactly behind its front. The instrument measures by how much, at ink
cost of line art only, so a run of sheets is affordable:

* page 1 is the sheet's FRONT: a bold solid line at each station;
* page 2 is the BACK, drawn in back-view frame (x mirrored, y kept): at each station a
  scale of +-N mm with a dashed zero. Held to light, the front's line reads directly on the
  back's scale; the signed reading is Delta-x, + = right as you view the back.
* a station may be a crosshair, read for Delta-y as well.

Nothing here is about any book: the station positions are arguments (Codex 0's bracket
the lantern chamber its cut lands on; that choice is the work's, kept in its own file).

``summarize`` turns a set of readings into the number to seat: mean and spread per
station and over the stations named as deciding. The marks read the PRINTER; they do not
respond to a seated offset (the proof of an offset is the thing it was for: the cut, the
facing art).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterable

SHEETS = {"letter-landscape": (11.0, 8.5), "letter": (8.5, 11.0), "a4-landscape": (11.693, 8.268),
          "a4": (8.268, 11.693)}
_LABEL_RE = re.compile(r"^[A-Za-z0-9-]{1,8}$")


class DuplexError(ValueError):
    pass


@dataclass(frozen=True)
class Station:
    label: str
    x: float          # inches from the FRONT's left edge
    y: float          # inches from the bottom edge
    cross: bool = False


def default_stations(width: float, height: float) -> list[Station]:
    """Three heights on each half of the sheet; the middle one a crosshair."""
    out = []
    for side, x in (("L", width * 0.25), ("R", width * 0.75)):
        for n, y in enumerate((height * 0.84, height * 0.5, height * 0.16), start=1):
            out.append(Station(f"{side}{n}", round(x, 3), round(y, 3), cross=(n == 2)))
    return out


def instrument_tex(stations: Iterable[Station], *, width: float, height: float, scale_mm: int = 10,
                   title: str = "DUPLEX REGISTRATION INSTRUMENT") -> str:
    stations = list(stations)
    if not 3 <= scale_mm <= 30:
        raise DuplexError("scale_mm must be between 3 and 30")
    for s in stations:
        if not _LABEL_RE.match(s.label):
            raise DuplexError(f"station label {s.label!r}: letters, digits and - only, up to 8")
        reach = 0.45 + scale_mm / 25.4
        if not (reach <= s.x <= width - reach and 0.45 <= s.y <= height - 0.45):
            raise DuplexError(f"station {s.label} at ({s.x}, {s.y}) in: its scale runs off the sheet")
    title = re.sub(r"[^A-Za-z0-9 .,:()-]", "", title)
    front, back = [], []
    for s in stations:
        bx = round(width - s.x, 4)
        if s.cross:
            front.append(f"\\FrontCross{{{s.x}}}{{{s.y}}}{{{s.label}}}")
            back.append(f"\\BackCross{{{bx}}}{{{s.y}}}{{{s.label}}}")
        else:
            front.append(f"\\FrontH{{{s.x}}}{{{s.y}}}{{{s.label}}}")
            back.append(f"\\BackH{{{bx}}}{{{s.y}}}{{{s.label}}}")
    N = int(scale_mm)
    return rf"""\documentclass{{article}}
\usepackage[paperwidth={width}in,paperheight={height}in,margin=0in]{{geometry}}
\usepackage{{tikz}}
\pagestyle{{empty}}
\setlength{{\parindent}}{{0pt}}
\def\MM{{0.0393701}}
\newcommand{{\FrontH}}[3]{{%
  \draw[line width=2pt] (#1,#2-0.24) -- (#1,#2+0.24);
  \node[anchor=west,font=\tiny] at (#1+0.07,#2+0.16) {{F#3}};}}
\newcommand{{\FrontCross}}[3]{{%
  \draw[line width=2pt] (#1,#2-0.40) -- (#1,#2+0.40);
  \draw[line width=2pt] (#1-0.40,#2) -- (#1+0.40,#2);
  \node[anchor=west,font=\tiny] at (#1+0.07,#2+0.32) {{F#3}};}}
\newcommand{{\ScaleX}}[2]{{%
  \draw[dash pattern=on 1.2pt off 1.2pt, line width=0.8pt] (#1,#2-0.24) -- (#1,#2+0.24);
  \foreach \m in {{-{N},...,{N}}}{{%
    \pgfmathsetmacro{{\tick}}{{ifthenelse(mod(abs(\m),5)==0,0.13,0.06)}}
    \draw[line width=0.5pt] (#1+\m*\MM,#2-\tick) -- (#1+\m*\MM,#2+\tick);}}
  \node[font=\tiny,anchor=north] at (#1-{N}*\MM,#2-0.14) {{$-{N}$}};
  \node[font=\tiny,anchor=north] at (#1+{N}*\MM,#2-0.14) {{$+{N}$}};}}
\newcommand{{\BackH}}[3]{{%
  \ScaleX{{#1}}{{#2}}
  \node[anchor=east,font=\tiny] at (#1-{N}*\MM-0.1,#2+0.16) {{#3}};}}
\newcommand{{\BackCross}}[3]{{%
  \ScaleX{{#1}}{{#2}}
  \draw[dash pattern=on 1.2pt off 1.2pt, line width=0.8pt] (#1,#2-0.44) -- (#1,#2+0.44);
  \draw[dash pattern=on 1.2pt off 1.2pt, line width=0.8pt] (#1-0.44,#2) -- (#1+0.44,#2);
  \foreach \m in {{-{N},...,{N}}}{{%
    \pgfmathsetmacro{{\tick}}{{ifthenelse(mod(abs(\m),5)==0,0.13,0.06)}}
    \draw[line width=0.5pt] (#1-\tick,#2+\m*\MM) -- (#1+\tick,#2+\m*\MM);}}
  \node[font=\tiny,anchor=west] at (#1+0.16,#2+{N}*\MM) {{$+{N}$ (up)}};
  \node[anchor=east,font=\tiny] at (#1-{N}*\MM-0.1,#2+0.16) {{#3}};}}
\begin{{document}}
\null
\begin{{tikzpicture}}[remember picture, overlay]
  \begin{{scope}}[shift={{(current page.south west)}},x=1in,y=1in]
    {chr(10).join("    " + line for line in front).strip()}
    \node[anchor=west,font=\scriptsize] at (0.5,0.22) {{{title} (front) --- marks only. Sheet \#\rule{{0.5in}}{{0.4pt}}\quad stock \rule{{1.0in}}{{0.4pt}}}};
  \end{{scope}}
\end{{tikzpicture}}
\clearpage
\null
\begin{{tikzpicture}}[remember picture, overlay]
  \begin{{scope}}[shift={{(current page.south west)}},x=1in,y=1in]
    {chr(10).join("    " + line for line in back).strip()}
    \node[anchor=west,font=\scriptsize] at (0.5,0.22) {{{title} (back) --- hold to light, this side up: read where each solid F line falls on its scale; $+$ = right as you view this side.}};
  \end{{scope}}
\end{{tikzpicture}}
\end{{document}}
"""


def render_instrument(output: Path, **kwargs: Any) -> Path:
    """Compile the instrument (two passes: tikz page anchors need them) to ``output``."""
    engine = shutil.which("lualatex") or shutil.which("xelatex")
    if engine is None:
        raise DuplexError("needs lualatex or xelatex")
    tex = instrument_tex(**kwargs)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="of_duplex_") as tmp:
        src = Path(tmp) / "instrument.tex"
        src.write_text(tex, encoding="utf-8")
        for _ in range(2):
            r = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", src.name],
                               cwd=tmp, capture_output=True, text=True, timeout=240)
            if r.returncode != 0:
                raise DuplexError("instrument did not compile: " + r.stdout[-800:])
        shutil.copyfile(Path(tmp) / "instrument.pdf", output)
    return output


def _stats(values: list[float]) -> dict[str, Any]:
    n = len(values)
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean_mm": round(mean, 3), "sd_mm": round(sd, 3),
            "min_mm": round(min(values), 3), "max_mm": round(max(values), 3)}


def summarize(readings: list[dict[str, Any]], *, deciding: list[str] | None = None) -> dict[str, Any]:
    """Readings ``[{sheet, station, dx_mm, dy_mm?}]`` -> per-station and deciding statistics.

    ``deciding`` names the stations whose mean is the number to seat (default: all).
    """
    if not readings:
        raise DuplexError("no readings")
    by: dict[str, list[float]] = {}
    dy: list[float] = []
    for r in readings:
        try:
            by.setdefault(str(r["station"]), []).append(float(r["dx_mm"]))
        except (KeyError, TypeError, ValueError):
            raise DuplexError(f"reading needs station and a numeric dx_mm: {r!r}") from None
        if r.get("dy_mm") is not None:
            dy.append(float(r["dy_mm"]))
    chosen = deciding or sorted(by)
    missing = [s for s in chosen if s not in by]
    if missing:
        raise DuplexError(f"deciding station(s) {missing} have no readings")
    pooled = [v for s in chosen for v in by[s]]
    return {"stations": {s: _stats(v) for s, v in sorted(by.items())},
            "deciding": chosen, "dx": _stats(pooled), "dy": _stats(dy) if dy else None,
            "sheets": len({r.get("sheet") for r in readings}),
            "seat_mm": round(sum(pooled) / len(pooled), 3)}
