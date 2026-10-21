"""Where a profile package lives (rulings 01a0f99a-b2db and 01a14634-bff0; SIL-32).

Profiles that left the engine keep their tests here, as codex0's did (tests/codex0_package.py):
the tests find the package through the same pointer the renderer uses, and skip on a host
without one.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def profile_package(profile_id: str, *, module_level: bool = False) -> Path:
    from engine.profile_resolver import resolve_profile

    try:
        package = resolve_profile(profile_id).boundary.get("profile_package")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"{profile_id} profile package not resolvable here: {exc}", allow_module_level=module_level)
    if not package:
        pytest.skip(f"{profile_id} profile package not resolvable here (no profile-repository pointer)",
                    allow_module_level=module_level)
    return Path(package)
