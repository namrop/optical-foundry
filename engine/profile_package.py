"""Profile packages: profiles kept in their own repositories.

Keeper ruling 01a0f99a-b2db: "I think the profiles should be in their own repo.
we can point to it. This will allow me to make a repo with public profiles."

A profile repository holds one directory per profile::

    <repo>/<profile-id>/profile.yaml

and the engine is pointed at any number of repositories, searched in order:

1. ``OF_PROFILE_PATH`` — a colon-separated list of repository paths;
2. ``$XDG_CONFIG_HOME/optical-foundry/profile_repos`` (default
   ``~/.config/optical-foundry/profile_repos``) — one repository path per line,
   ``#`` comments allowed. This is the per-host pointer.

An engine profile (``engine/profile_resolver.PROFILE_SPECS``) of the same id
wins: a package cannot shadow an engine profile silently.

``profile.yaml`` (schema ``profile_package_v1``)::

    schema_version: profile_package_v1
    id: keeper-capture
    title: ...
    extends: keeper              # an engine profile: its family, defaults and template
    template: null               # or a path in the package, replacing the extended one
    defaults: [defaults.yaml]    # paths in the package, appended to the extended stack
    source_preparation: null     # ruling 01a0f930-407c
    ornaments: {...}             # engine/ornaments.py
    openers: {...}               # engine/openers.py (map D4)
    markers: {prefix: cx0}       # engine/markers.py (map C2)
    family: document_spine       # G2: override the extended profile's family
    base_defaults: [a.yaml, ...] # G2: engine defaults to build on, replacing the extended stack
    tex: [tex]                   # G2: package directories on TEXINPUTS and LUAINPUTS
  A defaults file in a package names its own files as ${.}/... (pandoc's defaults-file
  directory), e.g. ``filters: [${.}/../filters/x.lua]``.
  Paths in profile.yaml are relative to the package and may name a sibling package in the same
  repository, e.g. ``defaults: ["../yugen-brand/defaults/yugenbase.yaml", defaults/keeper.yaml]``
  and ``tex: ["../yugen-brand/tex", "../yugen-brand"]`` (SIL-32): that is how a package builds on
  another package, since ``extends`` must name an engine profile. A package directory itself on
  ``tex`` puts its ``assets/...`` on TEXINPUTS, where raw LaTeX image paths resolve.
    editions: {labels: [...]}    # engine/editions.py (map C1)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "profile_package_v1"
_KEYS = {"schema_version", "id", "title", "description", "extends", "template", "defaults",
         "source_preparation", "ornaments", "openers", "markers", "editions",
         "family", "base_defaults", "tex", "divider_kinds"}


class ProfilePackageError(ValueError):
    pass


@dataclass(frozen=True)
class ProfilePackage:
    id: str
    directory: Path
    spec: dict[str, Any]


def profile_repositories() -> list[Path]:
    repos: list[Path] = []
    env = os.environ.get("OF_PROFILE_PATH", "")
    repos += [Path(p).expanduser() for p in env.split(":") if p.strip()]
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    pointer = config_home / "optical-foundry" / "profile_repos"
    if pointer.is_file():
        for line in pointer.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                repos.append(Path(line).expanduser())
    seen, out = set(), []
    for repo in repos:
        key = repo.resolve()
        if key not in seen:
            seen.add(key)
            out.append(repo)
    return out


def find_package(profile_id: str) -> ProfilePackage | None:
    for repo in profile_repositories():
        path = repo / profile_id / "profile.yaml"
        if path.is_file():
            return load_package(path)
    return None


def load_package(path: Path) -> ProfilePackage:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise ProfilePackageError(f"{path}: schema_version must be {SCHEMA}")
    unknown = set(data) - _KEYS
    if unknown:
        raise ProfilePackageError(f"{path}: unknown key(s) {sorted(unknown)}")
    if data.get("id") != path.parent.name:
        raise ProfilePackageError(f"{path}: id {data.get('id')!r} must match its directory {path.parent.name!r}")
    if not data.get("extends"):
        raise ProfilePackageError(f"{path}: extends must name an engine profile")
    if 'divider_kinds' in data:
        from engine.divider_kinds import validate_kinds
        try:
            validate_kinds(data['divider_kinds'], path.parent)
        except ValueError as exc:
            raise ProfilePackageError(f'{path}: {exc}') from exc
    return ProfilePackage(id=data["id"], directory=path.parent.resolve(), spec=data)
