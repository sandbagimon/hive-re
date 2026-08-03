from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

from simlab.models.scene import Scene


@dataclass(frozen=True, slots=True)
class RotorModel:
    """One quadratic rotor expressed in stable Scene robotics IDs."""

    id: str
    link_id: str
    actuator_id: str
    axis: tuple[float, float, float]
    direction: int
    thrust_coefficient: float
    torque_coefficient: float
    min_angular_velocity: float
    max_angular_velocity: float


@dataclass(frozen=True, slots=True)
class QuadrotorModel:
    """Transport-neutral parameters consumed by the MuJoCo adapter."""

    actor_id: str
    body_link_id: str
    rotors: tuple[RotorModel, RotorModel, RotorModel, RotorModel]


def quadrotor_models_from_scene(scene: Scene) -> tuple[QuadrotorModel, ...]:
    """Validate and load all actor-local quadratic quadrotor definitions."""

    link_ids = {
        link.id
        for articulation in (scene.robotics.articulations if scene.robotics else [])
        for link in articulation.links
    }
    actuator_ids = {
        actuator.id
        for articulation in (scene.robotics.articulations if scene.robotics else [])
        for actuator in articulation.actuators
    }
    models: list[QuadrotorModel] = []
    claimed_links: set[str] = set()
    claimed_actuators: set[str] = set()
    for actor in scene.actors:
        raw = actor.properties.get("propulsion")
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise ValueError(f"Actor propulsion must be an object: {actor.id}")
        if raw.get("type") != "quadrotor":
            continue
        if raw.get("model", "quadratic") != "quadratic":
            raise ValueError(f"Unsupported quadrotor propulsion model: {actor.id}")
        if raw.get("command_mode", "angular_velocity") != "angular_velocity":
            raise ValueError(f"Unsupported quadrotor command mode: {actor.id}")

        body_link_id = _required_id(raw, "body_link_id", actor.id)
        if body_link_id not in link_ids:
            raise ValueError(
                f"Quadrotor {actor.id} references unknown body link: {body_link_id}"
            )
        raw_rotors = raw.get("rotors")
        if not isinstance(raw_rotors, list) or len(raw_rotors) != 4:
            raise ValueError(f"Quadrotor {actor.id} must define exactly four rotors")
        rotors = cast(
            tuple[RotorModel, RotorModel, RotorModel, RotorModel],
            tuple(
                _parse_rotor(item, actor.id, link_ids, actuator_ids)
                for item in raw_rotors
            ),
        )
        rotor_ids = [item.id for item in rotors]
        rotor_links = [item.link_id for item in rotors]
        rotor_actuators = [item.actuator_id for item in rotors]
        for label, identifiers in (
            ("rotor", rotor_ids),
            ("rotor link", rotor_links),
            ("rotor actuator", rotor_actuators),
        ):
            if len(set(identifiers)) != 4:
                raise ValueError(f"Quadrotor {actor.id} {label} IDs must be unique")
        duplicate_links = sorted(set(rotor_links) & claimed_links)
        duplicate_actuators = sorted(set(rotor_actuators) & claimed_actuators)
        if duplicate_links or duplicate_actuators:
            duplicates = ", ".join(duplicate_links + duplicate_actuators)
            raise ValueError(f"Quadrotor propulsion resources are already claimed: {duplicates}")
        claimed_links.update(rotor_links)
        claimed_actuators.update(rotor_actuators)
        models.append(
            QuadrotorModel(
                actor_id=actor.id,
                body_link_id=body_link_id,
                rotors=rotors,
            )
        )
    return tuple(models)


def _parse_rotor(
    raw: Any,
    actor_id: str,
    link_ids: set[str],
    actuator_ids: set[str],
) -> RotorModel:
    if not isinstance(raw, dict):
        raise ValueError(f"Quadrotor {actor_id} rotor must be an object")
    rotor_id = _required_id(raw, "id", actor_id)
    link_id = _required_id(raw, "link_id", actor_id)
    actuator_id = _required_id(raw, "actuator_id", actor_id)
    if link_id not in link_ids:
        raise ValueError(f"Quadrotor {actor_id} rotor {rotor_id} has unknown link: {link_id}")
    if actuator_id not in actuator_ids:
        raise ValueError(
            f"Quadrotor {actor_id} rotor {rotor_id} has unknown actuator: {actuator_id}"
        )
    axis = _unit_vector(raw.get("axis", [0.0, 0.0, 1.0]), actor_id, rotor_id)
    direction = raw.get("direction")
    if isinstance(direction, bool) or direction not in (-1, 1):
        raise ValueError(
            f"Quadrotor {actor_id} rotor {rotor_id} direction must be -1 or 1"
        )
    thrust_coefficient = _positive_float(
        raw.get("thrust_coefficient"), "thrust_coefficient", actor_id, rotor_id
    )
    torque_coefficient = _nonnegative_float(
        raw.get("torque_coefficient", 0.0), "torque_coefficient", actor_id, rotor_id
    )
    minimum = _nonnegative_float(
        raw.get("min_angular_velocity", 0.0),
        "min_angular_velocity",
        actor_id,
        rotor_id,
    )
    maximum = _positive_float(
        raw.get("max_angular_velocity"),
        "max_angular_velocity",
        actor_id,
        rotor_id,
    )
    if minimum > maximum:
        raise ValueError(
            f"Quadrotor {actor_id} rotor {rotor_id} angular velocity range is invalid"
        )
    return RotorModel(
        id=rotor_id,
        link_id=link_id,
        actuator_id=actuator_id,
        axis=axis,
        direction=int(direction),
        thrust_coefficient=thrust_coefficient,
        torque_coefficient=torque_coefficient,
        min_angular_velocity=minimum,
        max_angular_velocity=maximum,
    )


def _required_id(data: dict[str, Any], key: str, actor_id: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Quadrotor {actor_id} {key} must be a non-empty string")
    return value


def _unit_vector(raw: Any, actor_id: str, rotor_id: str) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError(f"Quadrotor {actor_id} rotor {rotor_id} axis must contain xyz")
    try:
        values = tuple(float(value) for value in raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Quadrotor {actor_id} rotor {rotor_id} axis must be numeric"
        ) from exc
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"Quadrotor {actor_id} rotor {rotor_id} axis must be finite")
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        raise ValueError(f"Quadrotor {actor_id} rotor {rotor_id} axis must be non-zero")
    return cast(tuple[float, float, float], tuple(value / norm for value in values))


def _positive_float(raw: Any, key: str, actor_id: str, rotor_id: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Quadrotor {actor_id} rotor {rotor_id} {key} must be numeric"
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Quadrotor {actor_id} rotor {rotor_id} {key} must be > 0")
    return value


def _nonnegative_float(raw: Any, key: str, actor_id: str, rotor_id: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Quadrotor {actor_id} rotor {rotor_id} {key} must be numeric"
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Quadrotor {actor_id} rotor {rotor_id} {key} must be >= 0")
    return value
