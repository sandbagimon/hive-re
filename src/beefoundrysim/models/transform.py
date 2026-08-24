from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _vector3(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    vector = [float(item) for item in value]
    if len(vector) != 3:
        msg = f"Expected a 3-value vector, got {len(vector)} values"
        raise ValueError(msg)
    return vector


@dataclass(slots=True)
class Transform:
    """Position, Euler rotation, and scale for a scene actor."""

    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def __post_init__(self) -> None:
        self.position = _vector3(self.position, [0.0, 0.0, 0.0])
        self.rotation = _vector3(self.rotation, [0.0, 0.0, 0.0])
        self.scale = _vector3(self.scale, [1.0, 1.0, 1.0])

    def to_dict(self) -> dict[str, list[float]]:
        return {
            "position": list(self.position),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Transform:
        data = data or {}
        return cls(
            position=_vector3(data.get("position"), [0.0, 0.0, 0.0]),
            rotation=_vector3(data.get("rotation"), [0.0, 0.0, 0.0]),
            scale=_vector3(data.get("scale"), [1.0, 1.0, 1.0]),
        )
