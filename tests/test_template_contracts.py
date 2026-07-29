from pathlib import Path

GF = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = GF / "profiles" / "40_latex_import" / "templates" / "base.tex"
CODEX0_TEMPLATE = GF / "profiles" / "40_latex_import" / "templates" / "codex0.tex"
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
    assert "\\NewDocumentCommand{\\CodexOpenerEpigraph}{m m m m m m m}" in text
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
