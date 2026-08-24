from __future__ import annotations

import bisect
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from beefoundrysim.models.scene import Scene


@dataclass(frozen=True, slots=True)
class KinematicActorKeyframe:
    time: float
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class KinematicActorSample:
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    linear_velocity: tuple[float, float, float]
    angular_velocity: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class DynamicEventState:
    event_id: str
    actor_id: str
    label: str
    status: str
    progress: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "actor_id": self.actor_id,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
        }


@dataclass(frozen=True, slots=True)
class KinematicActorEvent:
    id: str
    actor_id: str
    label: str
    keyframes: tuple[KinematicActorKeyframe, ...]
    activation_time: float
    completion_time: float
    interpolation: str = "linear"

    def sample(self, time: float) -> KinematicActorSample:
        keyframes = self.keyframes
        if time <= keyframes[0].time:
            return _stationary_sample(keyframes[0])
        if time >= keyframes[-1].time:
            return _stationary_sample(keyframes[-1])

        upper = bisect.bisect_right([item.time for item in keyframes], time)
        start = keyframes[upper - 1]
        end = keyframes[upper]
        duration = end.time - start.time
        linear_progress = (time - start.time) / duration
        if self.interpolation == "smoothstep":
            progress = linear_progress * linear_progress * (3.0 - 2.0 * linear_progress)
            speed_scale = 6.0 * linear_progress * (1.0 - linear_progress) / duration
        else:
            progress = linear_progress
            speed_scale = 1.0 / duration
        position_delta = (
            end.position[0] - start.position[0],
            end.position[1] - start.position[1],
            end.position[2] - start.position[2],
        )
        rotation_delta = (
            end.rotation[0] - start.rotation[0],
            end.rotation[1] - start.rotation[1],
            end.rotation[2] - start.rotation[2],
        )
        return KinematicActorSample(
            position=(
                start.position[0] + position_delta[0] * progress,
                start.position[1] + position_delta[1] * progress,
                start.position[2] + position_delta[2] * progress,
            ),
            rotation=(
                start.rotation[0] + rotation_delta[0] * progress,
                start.rotation[1] + rotation_delta[1] * progress,
                start.rotation[2] + rotation_delta[2] * progress,
            ),
            linear_velocity=(
                position_delta[0] * speed_scale,
                position_delta[1] * speed_scale,
                position_delta[2] * speed_scale,
            ),
            angular_velocity=(
                rotation_delta[0] * speed_scale,
                rotation_delta[1] * speed_scale,
                rotation_delta[2] * speed_scale,
            ),
        )

    def state(self, time: float) -> DynamicEventState:
        if time < self.activation_time:
            status = "scheduled"
            progress = 0.0
        elif time >= self.completion_time:
            status = "completed"
            progress = 1.0
        else:
            status = "active"
            duration = self.completion_time - self.activation_time
            progress = (time - self.activation_time) / duration
        return DynamicEventState(
            event_id=self.id,
            actor_id=self.actor_id,
            label=self.label,
            status=status,
            progress=max(0.0, min(1.0, progress)),
        )


class KinematicActorEventScheduler:
    """Engine-neutral timeline for scene-authored moving physical actors."""

    def __init__(self, events: tuple[KinematicActorEvent, ...] = ()) -> None:
        event_ids = [event.id for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Dynamic event ids must be unique")
        actor_ids = [event.actor_id for event in events]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("Dynamic events may define only one timeline per actor")
        self.events = events
        self._events_by_actor = {event.actor_id: event for event in events}

    @classmethod
    def from_scene(cls, scene: Scene) -> KinematicActorEventScheduler:
        raw_events = scene.simulation_config.get("dynamic_events", [])
        if not isinstance(raw_events, list):
            raise ValueError("simulation_config.dynamic_events must be an array")
        actors_by_id = {actor.id: actor for actor in scene.actors}
        events = tuple(_parse_event(raw, actors_by_id) for raw in raw_events)
        return cls(events)

    @property
    def actor_ids(self) -> tuple[str, ...]:
        return tuple(self._events_by_actor)

    def sample(self, actor_id: str, time: float) -> KinematicActorSample:
        return self._events_by_actor[actor_id].sample(time)

    def states(self, time: float) -> list[DynamicEventState]:
        return [event.state(time) for event in self.events]


def _stationary_sample(keyframe: KinematicActorKeyframe) -> KinematicActorSample:
    return KinematicActorSample(
        position=keyframe.position,
        rotation=keyframe.rotation,
        linear_velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
    )


def _parse_event(raw: Any, actors_by_id: Mapping[str, Any]) -> KinematicActorEvent:
    if not isinstance(raw, Mapping):
        raise ValueError("Each dynamic event must be an object")
    event_type = raw.get("type", "kinematic_actor")
    if event_type != "kinematic_actor":
        raise ValueError(f"Unsupported dynamic event type: {event_type}")
    event_id = _non_empty_string(raw.get("id"), "Dynamic event id")
    actor_id = _non_empty_string(raw.get("actor_id"), f"Dynamic event {event_id} actor_id")
    actor = actors_by_id.get(actor_id)
    if actor is None:
        raise ValueError(f"Dynamic event {event_id} references unknown actor: {actor_id}")
    physics = actor.properties.get("physics")
    dynamic = not isinstance(physics, Mapping) or bool(physics.get("dynamic", True))
    if actor.type != "object" or not dynamic:
        raise ValueError(f"Dynamic event {event_id} actor must be dynamic: {actor_id}")
    label = _non_empty_string(raw.get("label", event_id), f"Dynamic event {event_id} label")
    raw_keyframes = raw.get("keyframes")
    if not isinstance(raw_keyframes, list) or len(raw_keyframes) < 2:
        raise ValueError(f"Dynamic event {event_id} requires at least two keyframes")
    keyframes = tuple(
        _parse_keyframe(item, event_id, index) for index, item in enumerate(raw_keyframes)
    )
    if any(
        current.time <= previous.time
        for previous, current in zip(keyframes, keyframes[1:], strict=False)
    ):
        raise ValueError(f"Dynamic event {event_id} keyframe times must increase")
    interpolation = str(raw.get("interpolation", "linear"))
    if interpolation not in {"linear", "smoothstep"}:
        raise ValueError(
            f"Dynamic event {event_id} interpolation must be linear or smoothstep"
        )
    activation_time = _finite_number(
        raw.get("activation_time", keyframes[0].time),
        f"Dynamic event {event_id} activation_time",
    )
    completion_time = _finite_number(
        raw.get("completion_time", keyframes[-1].time),
        f"Dynamic event {event_id} completion_time",
    )
    if activation_time < 0 or completion_time <= activation_time:
        raise ValueError(
            f"Dynamic event {event_id} activation/completion times are invalid"
        )
    if activation_time < keyframes[0].time or completion_time > keyframes[-1].time:
        raise ValueError(
            f"Dynamic event {event_id} active window must be covered by its keyframes"
        )
    return KinematicActorEvent(
        id=event_id,
        actor_id=actor_id,
        label=label,
        keyframes=keyframes,
        activation_time=activation_time,
        completion_time=completion_time,
        interpolation=interpolation,
    )


def _parse_keyframe(raw: Any, event_id: str, index: int) -> KinematicActorKeyframe:
    if not isinstance(raw, Mapping):
        raise ValueError(f"Dynamic event {event_id} keyframe {index} must be an object")
    time = _finite_number(raw.get("time"), f"Dynamic event {event_id} keyframe time")
    if time < 0:
        raise ValueError(f"Dynamic event {event_id} keyframe time must be >= 0")
    position = _finite_vector3(
        raw.get("position"), f"Dynamic event {event_id} keyframe position"
    )
    rotation = _finite_vector3(
        raw.get("rotation", [0.0, 0.0, 0.0]),
        f"Dynamic event {event_id} keyframe rotation",
    )
    return KinematicActorKeyframe(time=time, position=position, rotation=rotation)


def _finite_vector3(raw: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise ValueError(f"{label} must contain 3 numbers")
    return (
        _finite_number(raw[0], label),
        _finite_number(raw[1], label),
        _finite_number(raw[2], label),
    )


def _finite_number(raw: Any, label: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"{label} must be finite")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _non_empty_string(raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{label} must not be empty")
    return raw.strip()
