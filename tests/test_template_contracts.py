from pathlib import Path

GF = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = GF / "profiles" / "40_latex_import" / "templates" / "base.tex"
CODEX0_TEMPLATE = GF / "profiles" / "40_latex_import" / "templates" / "codex0.tex"
# The page-placement Lua, lifted out of codex0.tex on 2026-10-01 (architecture review candidate 5).
CODEX0_LUA_DIR = CODEX0_TEMPLATE.parents[1] / "styles" / "texmf" / "tex" / "latex" / "codex0"
CODEX0_ORNAMENT_LAW_LUA = CODEX0_LUA_DIR / "codex0_ornament_law.lua"
CODEX0_PLATE_FLOAT_LUA = CODEX0_LUA_DIR / "codex0_plate_float.lua"
CLIENT_TEMPLATE = GF / "profiles" / "40_latex_import" / "templates" / "client_report.tex"
CLIENT_STY = (
    GF / "profiles" / "40_latex_import" / "styles" / "texmf" / "tex" / "latex"
    / "client" / "clientcommon.sty"
)


def test_base_template_titlepage_logo_is_guarded_by_logo_path():
    """Neutral document-spine title pages must render without a logo asset."""
    text = BASE_TEMPLATE.read_text()
    include_idx = text.index("\\includegraphics[height=5cm]{$logo_path$}")
    before = text[:include_idx]
    after = text[include_idx:]

    assert before.rfind("$if(logo_path)$") > before.rfind("$if(titlepage)$")
    assert after.find("$endif$") < after.find("$if(title)")


def test_codex0_template_routes_verbatim_grinning_emoji_through_fallback_font():
    """U+1F601 in a text-message epigraph must not fall through to Iowan."""
    text = CODEX0_TEMPLATE.read_text()

    assert r"\newunicodechar{😁}{{\EmojiFont 😁}}" in text


def test_codex0_template_routes_verbatim_rainbow_emoji_through_fallback_font():
    """U+1F308 in a raw-LaTeX kept line must not fall through to Iowan."""
    text = CODEX0_TEMPLATE.read_text()

    assert r"\newunicodechar{🌈}{{\EmojiFont 🌈}}" in text


def test_codex0_defines_layered_opener_epigraph_grammar():
    """The 2026-07-28 layered chapter-opener epigraph macro must be defined with
    the register-inverted body, the small-caps speaker line, the middot
    bibliographic line, and the gold context line."""
    text = CODEX0_TEMPLATE.read_text()
    assert "\\NewDocumentCommand{\\CodexOpenerEpigraph}{m m m m m m m m}" in text
    # Register inversion: witness -> upright, else italic.
    assert "\\ifx\\CodexEpiReg\\CodexEpiWitnessName\\upshape\\else\\itshape\\fi" in text
    # Speaker line uses real small caps (Iowan Old Style carries smcp).
    assert "\\CodexSmallCaps{#3}" in text
    # Bibliographic line uses middot separators, no parentheses.
    assert "\\textperiodcentered" in text
    # Gold context line uses the LetterRule (gold) color.
    assert "\\textcolor{LetterRule}{#4}" in text
    # The generic body-prose quote grammar is left intact and separate.
    assert "\\NewDocumentCommand{\\CodexQuoteAttribution}{m m m}" in text


def test_client_kicker_uses_document_type_variable():
    """The cover kicker is frontmatter-driven, defaulting to SECURITY REPORT."""
    text = CLIENT_TEMPLATE.read_text()
    assert "$if(document_type)$$document_type$$else$SECURITY REPORT$endif$" in text
    # The old hard-coded "\quad REPORT" literal must be gone.
    assert "\\quad REPORT\\par" not in text


def test_client_pdf_metadata_hypersetup_present():
    text = CLIENT_TEMPLATE.read_text()
    for key in ("pdftitle", "pdfauthor", "pdfsubject", "pdfkeywords", "pdflang"):
        assert key in text, f"missing {key} in hypersetup"
    # hyperxmp must load after hyperref.
    assert text.index("\\usepackage{hyperref}") < text.index("\\usepackage{hyperxmp}")


def test_client_figure_counter_detached_from_chapter():
    text = CLIENT_TEMPLATE.read_text()
    assert "\\counterwithout{figure}{chapter}" in text
    assert "\\counterwithin{figure}{section}" in text  # section-scope branch


def test_client_toc_title_and_no_self_listing():
    text = CLIENT_TEMPLATE.read_text()
    assert "\\renewcommand{\\contentsname}{$if(toc-title)$$toc-title$$else$Contents$endif$}" in text
    # Starred form omits the Contents-in-Contents self entry.
    assert "\\tableofcontents*" in text


def test_codex0_template_applies_optional_body_folio_start_after_mainmatter_reset():
    """Frontmatter stays roman while a reading volume can continue body folios."""
    text = CODEX0_TEMPLATE.read_text()

    start = text.index("$if(body_folio_start)$")
    end = text.index("$endif$", start)
    block = text[start:end]
    assert r"\let\CodexOriginalMainmatter\mainmatter" in block
    unstarred = block[block.index(r"\newcommand{\CodexBodyMainmatter}"):]
    starred = block[block.index(r"\newcommand{\CodexBodyMainmatterStar}"):]
    assert unstarred.index(r"\CodexOriginalMainmatter") < unstarred.index(
        r"\setcounter{page}{$body_folio_start$}"
    )
    assert starred.index(r"\CodexOriginalMainmatter*") < starred.index(
        r"\setcounter{page}{$body_folio_start$}"
    )
    assert (
        r"\renewcommand{\mainmatter}{\@ifstar{\CodexBodyMainmatterStar}"
        r"{\CodexBodyMainmatter}}"
    ) in block


def test_client_footer_default_is_security():
    sty = CLIENT_STY.read_text()
    assert "\\providecommand{\\ClientDivision}{CLIENT}" in sty
    # Report-frontmatter footer override hooks exist in the template.
    text = CLIENT_TEMPLATE.read_text()
    assert "$if(footer_center)$\\renewcommand{\\ClientDivision}{$footer_center$}$endif$" in text
    assert "$if(classification_label)$\\renewcommand{\\ClientConfidentiality}{$classification_label$}$endif$" in text


# --- Ornament page-position law (Luis-ruled 2026-08-07) ---------------------


def test_codex0_template_registers_the_ornament_page_position_callback():
    """The law lives in a pre_output_filter, on the live LuaTeX page list.

    Anything less than a page-builder callback is guesswork: only the output
    routine knows where the page actually broke.
    """
    text = CODEX0_TEMPLATE.read_text()
    lua = CODEX0_ORNAMENT_LAW_LUA.read_text()

    assert "\\usepackage{luacode}" in text
    assert '\\directlua{require("codex0_ornament_law")}' in text
    assert 'luatexbase.new_attribute("codex0ornamentband")' in lua
    assert 'luatexbase.add_to_callback("pre_output_filter"' in lua
    assert "\\NewDocumentCommand{\\CodexOrnamentBand}{m +m}" in text
    assert "\\attributedef\\CodexOrnamentBandAttr" in text


def test_codex0_ornament_band_wrapper_is_never_a_body_providecommand():
    """\\CodexOrnamentBand must be template-only.

    A \\providecommand fallback in the body would let pandoc's latex_macros
    extension expand the wrapper at read time and strip the attribute before it
    ever reached the node list — the same failure mode that once ate
    \\CodexOpenerEpigraph.
    """
    compiler = (
        Path(__file__).resolve().parents[1] / "engine" / "manifest_compiler.py"
    ).read_text()
    layout = (
        Path(__file__).resolve().parents[1] / "engine" / "layout_images.py"
    ).read_text()

    assert "CodexOrnamentBand" not in compiler
    assert "CodexOrnamentBand" not in layout


def test_codex0_ornament_law_never_empties_a_page():
    """A page whose whole body is ornament is deliberate, not a stranding."""
    block = CODEX0_ORNAMENT_LAW_LUA.read_text()

    assert "if #doomed >= #bx then" in block
    assert "no other content -- left alone" in block


def test_codex0_ornament_law_keeps_the_first_structural_ornament_at_a_page_foot():
    """Tailpieces and thresholds may sit at a page foot — either/or, not both."""
    block = CODEX0_ORNAMENT_LAW_LUA.read_text()

    assert "kept_structural" in block
    assert "either/or" in block


def test_codex0_held_object_centres_between_its_anchors_by_construction():
    """A held object shorter than the measure must sit centred between the two
    anchors (Luis, build-64 proof, folios 115 and 137), and one that fills the
    measure must keep its justified full-measure setting.

    The construction — not a tuned offset — is: natural-width block (varwidth,
    capped at the measure) centred inside the measure, with the anchor seats
    pinned to the measure rather than to the block's own width."""
    text = CODEX0_TEMPLATE.read_text()
    block = text[
        text.index("\\newenvironment{CodexHeldObject}") : text.index(
            "\\newenvironment{CodexVowBlock}"
        )
    ]

    # The measure is a shared register, set from the live \linewidth.
    assert "\\usepackage{varwidth}" in text
    assert (
        "\\setlength{\\CodexHeldMeasure}{\\dimexpr\\linewidth-2\\CodexHeldIndent\\relax}"
        in block
    )
    # Natural-width block, capped at the measure — no fixed-width minipage.
    assert "\\begin{varwidth}{\\CodexHeldMeasure}" in block
    assert "\\begin{minipage}" not in block
    # ...centred inside the measure.
    assert "\\makebox[\\CodexHeldMeasure][c]{\\usebox{\\CodexHeldObjectBox}}" in block
    # The anchors stay in the gutters: seated off the measure, not the block.
    seat = text[
        text.index("\\newcommand{\\CodexManiculeSeat}") : text.index(
            "\\newenvironment{CodexVow}"
        )
    ]
    assert "\\hspace{\\dimexpr\\CodexHeldIndent+\\CodexHeldMeasure\\relax}" in seat
    assert "\\wd\\CodexHeldObjectBox" not in seat


def test_codex0_page_placement_lua_lives_in_files_the_template_requires(tmp_path):
    """No Lua is inlined in the template; each file parses and LuaTeX's kpse finds it."""
    import os
    import shutil
    import subprocess

    text = CODEX0_TEMPLATE.read_text()
    assert "\\begin{luacode*}" not in text
    for lua in (CODEX0_ORNAMENT_LAW_LUA, CODEX0_PLATE_FLOAT_LUA):
        assert f'\\directlua{{require("{lua.stem}")}}' in text
    if not (shutil.which("texlua") and shutil.which("kpsewhich")):
        return
    check = tmp_path / "parse.lua"
    check.write_text("for _, f in ipairs(arg) do assert(loadfile(f)) end\n", encoding="utf-8")
    subprocess.run(["texlua", str(check), str(CODEX0_ORNAMENT_LAW_LUA), str(CODEX0_PLATE_FLOAT_LUA)], check=True)
    env = {**os.environ, "TEXMFHOME": str(CODEX0_TEMPLATE.parents[1] / "styles" / "texmf")}
    found = subprocess.run(
        ["kpsewhich", "-progname=lualatex", "-format=lua", "codex0_ornament_law.lua", "codex0_plate_float.lua"],
        capture_output=True, text=True, env=env,
    ).stdout.split()
    assert [Path(f).resolve() for f in found] == [CODEX0_ORNAMENT_LAW_LUA.resolve(), CODEX0_PLATE_FLOAT_LUA.resolve()]
