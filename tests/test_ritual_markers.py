"""Read-time expansion must not consume a profile's ritual boundaries."""
import shutil
import subprocess

import pytest

from engine.manifest_compiler import _render_section_divider
from engine.template_contract import READ_TIME_DEFINITIONS


def test_ritual_markers_reach_latex():
    if not shutil.which("pandoc"):
        pytest.skip("pandoc is required for the read-time marker proof")
    source = "\n".join([
        *READ_TIME_DEFINITIONS,
        "",
        *_render_section_divider({"uid": "boundary-proof", "title": "Threshold", "force_right_page": False}),
    ])
    result = subprocess.run(
        ["pandoc", "--from=markdown+raw_tex+latex_macros", "--to=latex"],
        input=source, text=True, capture_output=True, check=True,
    )
    assert result.stdout.index(r"\clearpage") < result.stdout.index(r"\CodexPlateRitualBegin{}")
    assert r"\CodexPlateRitualBegin{}" in result.stdout
    assert r"\CodexPlateRitualEnd{}" in result.stdout
    assert result.stdout.index(r"\CodexPlateRitualBegin{}") < result.stdout.index("Threshold")
    assert result.stdout.index("Threshold") < result.stdout.index(r"\CodexPlateRitualEnd{}")
