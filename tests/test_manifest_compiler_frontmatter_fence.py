"""Frontmatter fence must be a line, not a substring.

Regression guard for build 65: a passage's prose_pass.objective quoted markdown
syntax (it recorded that it "struck the four body `---` thematic breaks"), the old
substring search matched that literal, the YAML truncated mid-value, safe_load
raised, and the whole file — frontmatter included — was emitted as body. Pandoc read
the in-body `title:` as document metadata and opened Volume I with a \\maketitle
title page.
"""
from engine.manifest_compiler import _split_frontmatter_and_body


def test_triple_dash_inside_a_yaml_value_does_not_end_the_frontmatter():
    text = (
        "---\n"
        "title: \"A Passage\"\n"
        "prose_pass:\n"
        "  objective: \"struck the four body `---` thematic breaks and merged the divs\"\n"
        "kind: note\n"
        "---\n"
        "\n"
        "::: {.codex-pataphorical}\n"
        "Body text survives.\n"
        ":::\n"
    )
    fm, body = _split_frontmatter_and_body(text)
    assert fm is not None, "frontmatter should parse despite the quoted --- in a value"
    assert fm["title"] == "A Passage"
    assert "`---`" in fm["prose_pass"]["objective"]
    assert "title:" not in body, "frontmatter must not leak into the body"
    assert "Body text survives." in body


def test_closing_fence_tolerates_trailing_whitespace():
    fm, body = _split_frontmatter_and_body("---\nkind: note\n---   \n\nbody\n")
    assert fm == {"kind": "note"}
    assert body.strip() == "body"


def test_no_closing_fence_returns_text_untouched():
    fm, body = _split_frontmatter_and_body("---\nkind: note\nno closing fence\n")
    assert fm is None
