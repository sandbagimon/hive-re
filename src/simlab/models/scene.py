from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simlab.models.actor import Actor
from simlab.models.attachment import Attachment, DeliveryTask
from simlab.models.robotics import RoboticsModel
from simlab.models.trajectory import SceneTrajectory


@dataclass(slots=True)
class Scene:
    """Canonical scene model serialized as scene.json."""

    version: str = "1.0"
    name: str = "Untitled Scene"
    units: str = "meters"
    actors: list[Actor] = field(default_factory=list)
    robotics: RoboticsModel | None = None
    trajectories: list[SceneTrajectory] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    delivery_tasks: list[DeliveryTask] = field(default_factory=list)
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
        if self.trajectories:
            data["trajectories"] = [item.to_dict() for item in self.trajectories]
        if self.attachments:
            data["attachments"] = [item.to_dict() for item in self.attachments]
        if self.delivery_tasks:
            data["delivery_tasks"] = [item.to_dict() for item in self.delivery_tasks]
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
            trajectories=[
                SceneTrajectory.from_dict(item) for item in data.get("trajectories", [])
            ],
            attachments=[Attachment.from_dict(item) for item in data.get("attachments", [])],
            delivery_tasks=[
                DeliveryTask.from_dict(item) for item in data.get("delivery_tasks", [])
            ],
            simulation_config=dict(data.get("simulation_config", {})),
        )
