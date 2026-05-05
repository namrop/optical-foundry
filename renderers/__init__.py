"""Renderer package for Optical Foundry greenfield.

Renderers accept a ProjectionPlan and produce rendered artifacts.

Phase 0: base contracts defined. Concrete renderers to follow as the
projection-plan → Pandoc dispatch matures.
"""

from renderers.base import Renderer

__all__ = ["Renderer"]
