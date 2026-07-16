from __future__ import annotations

import json
from pathlib import Path

from simlab.models.scene import Scene
from simlab.services.robotics_validation import validate_robotics_model
from simlab.services.trajectory_validation import (
    TrajectoryValidationError,
    validate_joint_trajectory,
)


class ProjectValidationError(ValueError):
    """Raised when a scene file fails minimal validation."""


def validate_scene(scene: Scene) -> None:
    """Validate invariants required by the scene.json format."""
    if not scene.version:
        raise ProjectValidationError("Scene must have a version")

    actor_ids = [actor.id for actor in scene.actors]
    if len(actor_ids) != len(set(actor_ids)):
        raise ProjectValidationError("Actor ids must be unique")

    if scene.robotics is not None:
        validate_robotics_model(scene.robotics)

    trajectory_ids = [item.id for item in scene.trajectories]
    if len(trajectory_ids) != len(set(trajectory_ids)):
        raise ProjectValidationError("Trajectory ids must be unique")

    actors_by_id = {actor.id: actor for actor in scene.actors}
    articulations_by_id = (
        {
            articulation.id: articulation
            for articulation in scene.robotics.articulations
        }
        if scene.robotics is not None
        else {}
    )
    for item in scene.trajectories:
        actor = actors_by_id.get(item.actor_id)
        if actor is None:
            raise ProjectValidationError(
                f"Trajectory {item.id} references unknown actor {item.actor_id}"
            )
        if actor.type != "robot":
            raise ProjectValidationError(
                f"Trajectory {item.id} actor {item.actor_id} must be a robot"
            )
        articulation_ids = actor.properties.get("articulation_ids", [])
        allowed_joint_ids = {
            actuator.joint_id
            for articulation_id in articulation_ids
            if (articulation := articulations_by_id.get(str(articulation_id)))
            for actuator in articulation.actuators
            if actuator.control_type == "position"
        }
        try:
            validate_joint_trajectory(
                item.trajectory,
                allowed_joint_ids=allowed_joint_ids,
            )
        except TrajectoryValidationError as exc:
            raise ProjectValidationError(f"Trajectory {item.id}: {exc}") from exc

    for actor in scene.actors:
        for name, vector in actor.transform.to_dict().items():
            if len(vector) != 3:
                raise ProjectValidationError(
                    f"Actor {actor.id} transform {name} must have 3 values"
                )


def save_scene(path: str | Path, scene: Scene) -> None:
    """Save a scene to pretty JSON."""
    validate_scene(scene)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scene.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_scene(path: str | Path) -> Scene:
    """Load and validate a scene from JSON."""
    input_path = Path(path)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    scene = Scene.from_dict(data)
    validate_scene(scene)
    return scene
