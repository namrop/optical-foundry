"""The template contract: every LaTeX command the engine emits, defined in one module.

Architecture review 2026-10-01, candidate 1 (ruling 01a0f8ba-4937). Two parts,
because pandoc treats them differently:

* ``contract_text()`` — ``engine/latex/template_contract.tex``, added to the end
  of every render's preamble (engine/preamble.py, origin ``contract``). Its
  ``\\providecommand`` defaults apply to any profile whose template or style
  package does not define the command; a profile restyles a command simply by
  defining it. These used to be copied into each template.

* ``READ_TIME_DEFINITIONS`` — written into the assembled bundle's body (by the
  bundle compiler, when the bundle has chapter openers or dividers). Pandoc's
  ``latex_macros`` extension reads these definitions and EXPANDS later calls
  to them while reading the Markdown, so for these commands the definition here
  is the one that sets, even where a template defines a richer version (the
  2026-07-25 \\OFChapterOpener and 2026-08-06 \\CodexOpenerEpigraph findings).
  Moving them into the preamble would hand those calls to the templates and
  change how Codex 0 sets; that is a separate decision.

  Known consequence (found 2026-10-01): pandoc also expands the divider calls
  ``\\CodexPlateRitualBegin{}`` / ``\\CodexPlateRitualEnd{}`` to nothing, so
  codex0's Lua-backed ritual no-inject zone never receives them in a bundle.
  Recorded, not changed here.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parent / "latex" / "template_contract.tex"


@lru_cache(maxsize=1)
def contract_text() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8").rstrip("\n")


READ_TIME_DEFINITIONS: list[str] = [
    # Ritual no-inject zone marks (codex0 defines the Lua-backed versions).
    "\\providecommand{\\CodexPlateRitualBegin}{}",
    "\\providecommand{\\CodexPlateRitualEnd}{}",
    "\\providecommand{\\OFChapterOpener}[1]{{\\par\\bigskip\\begingroup\\centering\\Large #1\\par\\endgroup\\medskip}}",
    "\\providecommand{\\OFChapterOpenerEpigraph}[2]{{\\par\\bigskip\\begingroup\\centering\\Large #1\\par\\smallskip\\small\\itshape #2\\par\\endgroup\\medskip}}",
    # Fallbacks so a non-codex0 profile can still render a codex-quote epigraph
    # beneath the opener heading. codex0 defines richer versions; these only
    # apply if the profile left them undefined. The attribution fallback mirrors
    # codex0's empty-author handling (emdash+author when author present, else
    # italic source), so source/date survive even without an author.
    "\\providecommand{\\CodexQuoteAttribution}[3]{{\\par\\smallskip{\\raggedleft\\small"
    "\\if\\relax\\detokenize{#1}\\relax\\if\\relax\\detokenize{#2}\\relax\\else\\emph{#2}\\fi"
    "\\else\\textemdash{} #1\\if\\relax\\detokenize{#2}\\relax\\else, \\emph{#2}\\fi\\fi"
    "\\if\\relax\\detokenize{#3}\\relax\\else\\ (#3)\\fi\\par}}}",
    "\\ifdefined\\CodexQuoteBlock\\else\\newenvironment{CodexQuoteBlock}[3]{\\par\\medskip\\begin{quote}\\itshape}{\\end{quote}\\par\\medskip}\\fi",
    # Layered chapter-opener epigraph (2026-07-28 grammar). codex0 defines the
    # rich version (small-caps speaker line, middot bibliographic line, gold
    # context line, register-inverted body); this fallback keeps any other
    # profile safe with a best-effort italic body + em-dash attribution.
    # Args: {register}{text}{speaker}{context}{author}{source}{date}
    #
    # ⚠ THIS FALLBACK IS THE LIVE PATH for the codex0 book, and has been since
    # the grammar landed (found 2026-08-06, print-eve A/B: template hook at 20em
    # produced byte-identical geometry). Pandoc's latex_macros extension reads
    # this providecommand and EXPANDS \CodexOpenerEpigraph calls at READ time,
    # so the template's \NewDocumentCommand (codex0.tex:857) never sees a call.
    # Same mechanism as the 2026-07-25 \OFChapterOpener detection note. That is
    # why the 2026-08-03 gap ruling (2.2em) and the 2026-08-06 doubling (4.4em)
    # were both inert, and why witness epigraphs print italic against the
    # template contract. The \ifdefined guard below survives pandoc's textual
    # expansion into the emitted .tex and evaluates at COMPILE time, so the
    # template-side \CodexEpigraphToBodyGap hook (Luis-ruled 2026-08-06:
    # doubled) is now honoured on the live path while any template-less profile
    # still degrades to \smallskip. Full grammar activation (register inversion,
    # smallcaps, gold context line) remains a separate decision — it would
    # restyle 78 openers sight-unseen and is NOT taken here.
    "\\providecommand{\\CodexSmallCaps}[1]{\\textsc{#1}}",
    "\\providecommand{\\CodexOpenerEpigraph}[8]{{\\par\\smallskip"
    "\\begin{quote}\\itshape #2\\end{quote}"
    "{\\raggedleft"
    "\\if\\relax\\detokenize{#3}\\relax\\else{\\small\\textemdash{}~\\textsc{#3}"
    "\\if\\relax\\detokenize{#4}\\relax\\else, #4\\fi\\par}\\fi"
    "{\\footnotesize"
    "\\if\\relax\\detokenize{#3}\\relax\\textemdash{}~\\fi"
    "\\if\\relax\\detokenize{#5}\\relax\\else#5\\fi"
    "\\if\\relax\\detokenize{#6}\\relax\\else\\space\\textperiodcentered\\space\\emph{#6}\\fi"
    "\\if\\relax\\detokenize{#7}\\relax\\else\\space\\textperiodcentered\\space tr.~#7\\fi"
    "\\if\\relax\\detokenize{#8}\\relax\\else\\space\\textperiodcentered\\space#8\\fi\\par}"
    "\\par}"
    "\\ifdefined\\CodexEpigraphToBodyGap\\CodexEpigraphToBodyGap\\fi}}",
]
