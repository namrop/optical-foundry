from pathlib import Path

import pytest

from renderers import document_renderer
from renderers.document_renderer import DocumentRenderer
from renderers.pandoc_renderer import PandocRenderer


class RecordingPandocRenderer:
    plans = []

    def render(self, plan, output_dir=None):
        self.__class__.plans.append(plan)
        return {"status": "ok", "render_id": plan.render_id, "plan_toc": plan.toc}


def _codex0_template():
    """codex0.tex, from the codex0 profile package (map G2)."""
    from tests.codex0_package import codex0_package

    return codex0_package() / "templates" / "codex0.tex"


@pytest.fixture(autouse=True)
def reset_recorded_plans(monkeypatch):
    RecordingPandocRenderer.plans = []
    monkeypatch.setattr(document_renderer, "PandocRenderer", RecordingPandocRenderer)


def test_stationery_letter_profiles_default_to_no_toc_when_source_is_silent(tmp_path):
    source = tmp_path / "letter.md"
    source.write_text("---\nuid: letter-test\ntitle: Letter Test\n---\n\nMy love,\n\nBody.")

    for profile in ["mythic-letter", "mythic-letter-johannah"]:
        DocumentRenderer().render(source, profile_id=profile, output_dir=str(tmp_path / profile))

    assert [plan.profile_id for plan in RecordingPandocRenderer.plans] == [
        "mythic-letter",
        "mythic-letter-johannah",
    ]
    assert [plan.toc for plan in RecordingPandocRenderer.plans] == [False, False]


def test_explicit_source_toc_still_overrides_letter_profile_default(tmp_path):
    source = tmp_path / "letter-with-toc.md"
    source.write_text("---\nuid: letter-test\ntitle: Letter Test\ntoc: true\n---\n\n# Body\n")

    DocumentRenderer().render(source, profile_id="mythic-letter-johannah", output_dir=str(tmp_path))

    assert RecordingPandocRenderer.plans[-1].toc is True


def test_johannah_letter_template_keeps_body_clear_of_header_rule():
    template = Path("profiles/40_latex_import/templates/mythic_letter_johannah.tex").read_text()

    assert "\\vspace*{-" not in template
    assert "$if(body_top_vspace)$" in template
    assert "\\vspace*{$body_top_vspace$}" in template


def test_codex0_template_suppresses_running_header_and_footer_rules():
    template = _codex0_template().read_text()
    start = template.index("\\fancypagestyle{codexArtifact}")
    end = template.index("% Pass Pandoc variables", start)
    codex_artifact_style = template[start:end]

    assert "\\renewcommand{\\headrulewidth}{0pt}" in codex_artifact_style
    assert "\\renewcommand{\\footrulewidth}{0pt}" in codex_artifact_style
    assert "\\leaders\\hrule" not in codex_artifact_style
    assert "LetterRule" not in codex_artifact_style
    assert "\\fancyhead[LE]" in codex_artifact_style
    assert "\\fancyhead[RO]" in codex_artifact_style
    assert "\\fancyhead[L]" not in codex_artifact_style
    assert "\\fancyhead[R]" not in codex_artifact_style


def test_letter_frontmatter_template_variables_are_materialized(tmp_path):
    source = tmp_path / "letter-frontmatter-vars.md"
    source.write_text(
        "---\n"
        "uid: letter-test\n"
        "title: Letter Test\n"
        "artifact_series: \"Letter #3 Example\"\n"
        "penned_date: \"2025-10-25\"\n"
        "render_title: true\n"
        "---\n\n"
        "Body.\n",
        encoding="utf-8",
    )

    defaults = PandocRenderer._frontmatter_variables_defaults(source, tmp_path, "letter-test")

    assert defaults is not None
    text = defaults.read_text(encoding="utf-8")
    assert "artifact_series: Letter \\#3 Example" in text
    assert "penned_date: '2025-10-25'" in text
    assert "render_title: true" in text
