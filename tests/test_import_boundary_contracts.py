from pathlib import Path

GF = Path(__file__).resolve().parents[1]
DEFAULTS = GF / "profiles" / "40_latex_import" / "defaults"


def test_imported_defaults_do_not_reference_legacy_40_latex_absolute_asset_paths():
    offenders = []
    for path in sorted(DEFAULTS.glob("*.yaml")):
        text = path.read_text()
        if "~/Digital_Workspace/40_latex" in text:
            offenders.append(path.name)
    assert offenders == []
