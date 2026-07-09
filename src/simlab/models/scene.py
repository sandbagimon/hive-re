from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simlab.models.actor import Actor


@dataclass(slots=True)
class Scene:
    """Canonical scene model serialized as scene.json."""

    version: str = "1.0"
    name: str = "Untitled Scene"
    units: str = "meters"
    actors: list[Actor] = field(default_factory=list)
    simulation_config: dict[str, Any] = field(
        default_factory=lambda: {"timestep": 0.01, "duration": 1.0}
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "units": self.units,
            "actors": [actor.to_dict() for actor in self.actors],
            "simulation_config": self.simulation_config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        return cls(
            version=str(data["version"]),
            name=str(data.get("name", "Untitled Scene")),
            units=str(data.get("units", "meters")),
            actors=[Actor.from_dict(actor) for actor in data.get("actors", [])],
            simulation_config=dict(data.get("simulation_config", {})),
        )
