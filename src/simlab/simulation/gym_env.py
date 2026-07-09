from __future__ import annotations

from typing import Any


class SimLabEnv:
    """Small future-extension stub for a gym-style environment."""

    def reset(self) -> dict[str, Any]:
        return {"observation": None}

    def step(self, action: Any) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        return {"observation": action}, 0.0, False, False, {}

    def close(self) -> None:
        return None
