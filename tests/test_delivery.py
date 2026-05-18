from engine.delivery import insert_title_verso_colophon, suppress_bound_pagination_overrides, inject_bound_running_header_marks


def test_insert_title_verso_colophon_avoids_nesting_raw_latex_fences():
    body = """```{=latex}
\\begin{center}
Title
\\end{center}
\\clearpage
```

## Chapter I
"""
    colophon = """```{=latex}
\\OFBoundColophon
\\clearpage
```"""

    assembled, inserted = insert_title_verso_colophon(body, colophon)

    assert inserted is True
    assert "\\clearpage\n```\n\n```{=latex}\n\\OFBoundColophon" in assembled
    assert "\\clearpage\n\n```{=latex}" not in assembled


def test_suppress_bound_pagination_overrides_removes_enlargethispage_commands():
    body = (
        "Lead paragraph.\n\n"
        "\\enlargethispage{3\\baselineskip}\n\n"
        "Body that should not be pushed into the page-number lane.\n"
        "Inline preservation: \\clearpage remains authored.\n"
    )

    stripped, evidence = suppress_bound_pagination_overrides(body)

    assert "\\enlargethispage" not in stripped
    assert "Body that should not be pushed" in stripped
    assert "\\clearpage remains authored" in stripped
    assert evidence == {
        "policy": "suppress_bound_unsafe",
        "enlargethispage_suppressed": 1,
        "commands_suppressed": ["enlargethispage"],
    }


def test_inject_bound_running_header_marks_adds_chapter_marks_after_headings():
    body = "## Chapter I — The Three Roads\n\nBody.\n\n## Not a Chapter\n\nMore.\n"

    marked, evidence = inject_bound_running_header_marks(body, source="chapter")

    assert "## Chapter I — The Three Roads\n\n```{=latex}\n\\markboth{Chapter I — The Three Roads}{Chapter I — The Three Roads}\n```" in marked
    assert "\\markboth{Not a Chapter}" not in marked
    assert evidence == {
        "enabled": True,
        "source": "chapter",
        "marks_inserted": 1,
    }
