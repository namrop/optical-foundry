"""Where the codex0 profile package lives (map G2: it left the engine on 2026-10-03).

Codex 0's tests stay in the engine repository, because they exercise engine behaviour on
the engine's most demanding profile; they find the profile through the same pointer the
renderer uses, and skip on a host without one.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def codex0_package() -> Path:
    from engine.profile_resolver import resolve_profile

    try:
        package = resolve_profile("codex0").boundary.get("profile_package")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"codex0 profile package not resolvable here: {exc}")
    if not package:
        pytest.skip("codex0 profile package not resolvable here (no profile-repository pointer)")
    return Path(package)
