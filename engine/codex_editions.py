"""Codex 0's name for engine/editions.py (moved and generalized 2026-10-03, map C1/C2)."""
import engine.editions as _editions

globals().update({k: v for k, v in vars(_editions).items() if not k.startswith("__")})
