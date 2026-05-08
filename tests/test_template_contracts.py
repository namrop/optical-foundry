from pathlib import Path

GF = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = GF / "profiles" / "40_latex_import" / "templates" / "base.tex"


def test_base_template_titlepage_logo_is_guarded_by_logo_path():
    """Neutral document-spine title pages must render without a logo asset."""
    text = BASE_TEMPLATE.read_text()
    include_idx = text.index("\\includegraphics[height=5cm]{$logo_path$}")
    before = text[:include_idx]
    after = text[include_idx:]

    assert before.rfind("$if(logo_path)$") > before.rfind("$if(titlepage)$")
    assert after.find("$endif$") < after.find("$if(title)")
