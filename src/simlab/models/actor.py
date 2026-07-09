from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from simlab.models.transform import Transform

ActorType = Literal["object", "robot", "terrain", "camera", "light"]
ACTOR_TYPES = {"object", "robot", "terrain", "camera", "light"}


@dataclass(slots=True)
class Actor:
    """A single object in a SimLab scene."""

    id: str
    name: str
    type: ActorType
    asset_id: str
    transform: Transform = field(default_factory=Transform)
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in ACTOR_TYPES:
            msg = f"Unsupported actor type: {self.type}"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "asset_id": self.asset_id,
            "transform": self.transform.to_dict(),
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Actor:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            type=data["type"],
            asset_id=str(data.get("asset_id", "")),
            transform=Transform.from_dict(data.get("transform")),
            properties=dict(data.get("properties", {})),
        )
