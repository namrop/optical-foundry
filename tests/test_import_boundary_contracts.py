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


def test_runtime_code_does_not_reference_external_legacy_profile_tree():
    offenders = []
    legacy_path = "~/Digital_Workspace/40_latex"
    for root in [GF / "engine", GF / "renderers", GF / "cli"]:
        for path in sorted(root.rglob("*.py")):
            if legacy_path in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(GF)))
    assert offenders == []
