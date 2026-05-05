"""Base renderer contract.

Concrete renderers implement `render` which takes a ProjectionPlan and returns
an evidence dict recording output metadata, integrity checks, and boundary
assertions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from engine.projection_plan import ProjectionPlan


class Renderer(ABC):
    """Abstract base for all renderer implementations."""

    name: str = "base"

    @abstractmethod
    def render(self, plan: ProjectionPlan, output_dir: str | None = None) -> dict[str, Any]:
        """Execute the render and return an evidence dict."""
