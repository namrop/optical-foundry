#!/usr/bin/env python3
"""Render the bundled example without consulting host profile repositories."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    example = Path(__file__).resolve().parent
    root = example.parents[1]
    output = root / "generated" / "illuminated-book"
    output.mkdir(parents=True, exist_ok=True)
    # A temporary home/config makes discovery independent of the caller's setup.
    # The only pointer names the profile package committed beside this script.
    with tempfile.TemporaryDirectory(prefix="example-home-", dir=output) as home:
        config = Path(home) / ".config"
        pointer = config / "optical-foundry" / "profile_repos"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(str(example / "profiles") + "\n", encoding="utf-8")
        env = dict(os.environ)
        env.pop("OF_PROFILE_PATH", None)
        env.pop("PYTHONPATH", None)
        env.update(HOME=home, XDG_CONFIG_HOME=str(config),
                   XDG_CACHE_HOME=str(Path(home) / ".cache"))
        command = [sys.executable, "-m", "cli", "manifest",
                   str(example / "book.yaml"), "--output", str(output)]
        print("Using only the bundled illuminated-example profile.", flush=True)
        return subprocess.run(command, cwd=root, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
