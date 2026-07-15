from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simlab.models.actor import Actor
from simlab.models.robotics import RoboticsModel


@dataclass(slots=True)
class Scene:
    """Canonical scene model serialized as scene.json."""

    version: str = "1.0"
    name: str = "Untitled Scene"
    units: str = "meters"
    actors: list[Actor] = field(default_factory=list)
    robotics: RoboticsModel | None = None
    simulation_config: dict[str, Any] = field(
        default_factory=lambda: {"timestep": 0.01, "duration": 1.0}
    )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": self.version,
            "name": self.name,
            "units": self.units,
            "actors": [actor.to_dict() for actor in self.actors],
            "simulation_config": self.simulation_config,
        }
        if self.robotics is not None:
            data["robotics"] = self.robotics.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        return cls(
            version=str(data["version"]),
            name=str(data.get("name", "Untitled Scene")),
            units=str(data.get("units", "meters")),
            actors=[Actor.from_dict(actor) for actor in data.get("actors", [])],
            robotics=(
                RoboticsModel.from_dict(data["robotics"])
                if data.get("robotics") is not None
                else None
            ),
            simulation_config=dict(data.get("simulation_config", {})),
        )
