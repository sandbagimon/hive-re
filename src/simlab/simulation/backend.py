from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, cast, runtime_checkable

from simlab.models.scene import Scene


class SimulationBackendError(RuntimeError):
    """Base error raised by an engine or transport adapter."""


class BackendSessionClosedError(SimulationBackendError):
    """Raised when a closed simulation session is used."""


class ModelSchemaMismatchError(SimulationBackendError):
    """Raised when a command was produced for a different model schema."""


class InvalidControlError(SimulationBackendError, ValueError):
    """Raised when an actuator control vector is malformed or out of range."""


@dataclass(frozen=True, slots=True)
class BoundedArraySpec:
    """Engine-neutral description of one dense numeric tensor."""

    shape: tuple[int, ...]
    minimum: tuple[float, ...]
    maximum: tuple[float, ...]
    dtype: str = "float32"

    def __post_init__(self) -> None:
        if not self.shape or any(size < 1 for size in self.shape):
            raise ValueError("Array spec shape dimensions must be >= 1")
        size = math.prod(self.shape)
        if len(self.minimum) != size or len(self.maximum) != size:
            raise ValueError("Array spec bounds must match the flattened shape")
        if any(low > high for low, high in zip(self.minimum, self.maximum, strict=True)):
            raise ValueError("Array spec minimum must not exceed maximum")


@dataclass(frozen=True, slots=True)
class BodyDescription:
    id: str


@dataclass(frozen=True, slots=True)
class JointDescription:
    id: str
    lower: float | None = None
    upper: float | None = None


@dataclass(frozen=True, slots=True)
class ActuatorDescription:
    id: str
    joint_id: str
    control_type: str
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not self.id or not self.joint_id:
            raise ValueError("Actuator and joint IDs must not be empty")
        if not math.isfinite(self.lower) or not math.isfinite(self.upper):
            raise ValueError("Actuator control bounds must be finite")
        if self.lower > self.upper:
            raise ValueError("Actuator lower control bound must not exceed upper bound")


@dataclass(frozen=True, slots=True)
class ModelDescription:
    """Stable model layout shared by local and remote simulation backends."""

    backend_name: str
    backend_version: str
    timestep: float
    scene_hash: str
    schema_hash: str
    bodies: tuple[BodyDescription, ...]
    joints: tuple[JointDescription, ...]
    actuators: tuple[ActuatorDescription, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.timestep) or self.timestep <= 0:
            raise ValueError("Model timestep must be finite and > 0")
        for kind, identifiers in (
            ("body", [item.id for item in self.bodies]),
            ("joint", [item.id for item in self.joints]),
            ("actuator", [item.id for item in self.actuators]),
        ):
            if any(not identifier for identifier in identifiers):
                raise ValueError(f"Model {kind} IDs must not be empty")
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"Model {kind} IDs must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_name": self.backend_name,
            "backend_version": self.backend_version,
            "timestep": self.timestep,
            "scene_hash": self.scene_hash,
            "schema_hash": self.schema_hash,
            "bodies": [{"id": item.id} for item in self.bodies],
            "joints": [
                {"id": item.id, "lower": item.lower, "upper": item.upper} for item in self.joints
            ],
            "actuators": [
                {
                    "id": item.id,
                    "joint_id": item.joint_id,
                    "control_type": item.control_type,
                    "lower": item.lower,
                    "upper": item.upper,
                }
                for item in self.actuators
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelDescription:
        return cls(
            backend_name=str(data["backend_name"]),
            backend_version=str(data["backend_version"]),
            timestep=float(data["timestep"]),
            scene_hash=str(data["scene_hash"]),
            schema_hash=str(data["schema_hash"]),
            bodies=tuple(BodyDescription(id=str(item["id"])) for item in data["bodies"]),
            joints=tuple(
                JointDescription(
                    id=str(item["id"]),
                    lower=(float(item["lower"]) if item.get("lower") is not None else None),
                    upper=(float(item["upper"]) if item.get("upper") is not None else None),
                )
                for item in data["joints"]
            ),
            actuators=tuple(
                ActuatorDescription(
                    id=str(item["id"]),
                    joint_id=str(item["joint_id"]),
                    control_type=str(item["control_type"]),
                    lower=float(item["lower"]),
                    upper=float(item["upper"]),
                )
                for item in data["actuators"]
            ),
        )


@dataclass(frozen=True, slots=True)
class BackendState:
    """Compact, immutable algorithm data plane in model-description order."""

    schema_hash: str
    time: float
    step_index: int
    joint_positions: tuple[float, ...]
    joint_velocities: tuple[float, ...]
    actuator_controls: tuple[float, ...]
    actuator_forces: tuple[float, ...]
    body_positions: tuple[tuple[float, float, float], ...]
    body_quaternions: tuple[tuple[float, float, float, float], ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.time) or self.time < 0:
            raise ValueError("Backend state time must be finite and >= 0")
        if self.step_index < 0:
            raise ValueError("Backend state step_index must be >= 0")
        values = (
            *self.joint_positions,
            *self.joint_velocities,
            *self.actuator_controls,
            *self.actuator_forces,
            *(value for position in self.body_positions for value in position),
            *(value for quaternion in self.body_quaternions for value in quaternion),
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Backend state values must be finite")
        if len(self.body_positions) != len(self.body_quaternions):
            raise ValueError("Backend body position and quaternion counts must match")
        if any(len(item) != 3 for item in self.body_positions):
            raise ValueError("Backend body positions must contain xyz triples")
        if any(len(item) != 4 for item in self.body_quaternions):
            raise ValueError("Backend body quaternions must contain wxyz quadruples")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_hash": self.schema_hash,
            "time": self.time,
            "step_index": self.step_index,
            "joint_positions": list(self.joint_positions),
            "joint_velocities": list(self.joint_velocities),
            "actuator_controls": list(self.actuator_controls),
            "actuator_forces": list(self.actuator_forces),
            "body_positions": [list(item) for item in self.body_positions],
            "body_quaternions": [list(item) for item in self.body_quaternions],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BackendState:
        return cls(
            schema_hash=str(data["schema_hash"]),
            time=float(data["time"]),
            step_index=int(data["step_index"]),
            joint_positions=tuple(float(value) for value in data["joint_positions"]),
            joint_velocities=tuple(float(value) for value in data["joint_velocities"]),
            actuator_controls=tuple(float(value) for value in data["actuator_controls"]),
            actuator_forces=tuple(float(value) for value in data["actuator_forces"]),
            body_positions=tuple(
                cast(
                    tuple[float, float, float],
                    tuple(float(value) for value in item),
                )
                for item in data["body_positions"]
            ),
            body_quaternions=tuple(
                cast(
                    tuple[float, float, float, float],
                    tuple(float(value) for value in item),
                )
                for item in data["body_quaternions"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ControlCommand:
    """One complete actuator vector bound to a model schema."""

    schema_hash: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.schema_hash:
            raise ValueError("Control command schema_hash must not be empty")
        if any(not math.isfinite(value) for value in self.values):
            raise InvalidControlError("Actuator controls must be finite")


@dataclass(frozen=True, slots=True)
class ResetOptions:
    """Named initial state overrides with no engine-specific indexes."""

    joint_positions: Mapping[str, float] = field(default_factory=dict)
    joint_velocities: Mapping[str, float] = field(default_factory=dict)
    actuator_controls: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("joint_positions", "joint_velocities", "actuator_controls"):
            raw = getattr(self, field_name)
            values = {str(key): float(value) for key, value in (raw or {}).items()}
            if any(not key for key in values):
                raise ValueError(f"Reset option {field_name} IDs must not be empty")
            if any(not math.isfinite(value) for value in values.values()):
                raise ValueError(f"Reset option {field_name} values must be finite")
            object.__setattr__(self, field_name, MappingProxyType(values))

    @classmethod
    def from_mapping(cls, options: Mapping[str, Any] | None) -> ResetOptions:
        options = options or {}
        return cls(
            joint_positions=options.get("joint_positions") or {},
            joint_velocities=options.get("joint_velocities") or {},
            actuator_controls=options.get("actuator_controls") or {},
        )


@dataclass(frozen=True, slots=True)
class SceneBundle:
    """Immutable scene revision passed to any backend implementation."""

    scene_json: str
    scene_hash: str
    asset_root: str | None = None
    export_path: str | None = None

    @classmethod
    def from_scene(
        cls,
        scene: Scene,
        *,
        asset_root: str | Path | None = None,
        export_path: str | Path | None = None,
    ) -> SceneBundle:
        scene_json = json.dumps(
            scene.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return cls(
            scene_json=scene_json,
            scene_hash=hashlib.sha256(scene_json.encode("utf-8")).hexdigest(),
            asset_root=str(Path(asset_root).resolve()) if asset_root is not None else None,
            export_path=str(Path(export_path).resolve()) if export_path is not None else None,
        )

    def scene(self) -> Scene:
        actual = hashlib.sha256(self.scene_json.encode("utf-8")).hexdigest()
        if actual != self.scene_hash:
            raise SimulationBackendError("Scene bundle content hash does not match payload")
        return Scene.from_dict(json.loads(self.scene_json))


@runtime_checkable
class SimulationBackendSession(Protocol):
    @property
    def model_description(self) -> ModelDescription: ...

    def reset(
        self,
        *,
        seed: int | None = None,
        options: ResetOptions | None = None,
    ) -> BackendState: ...

    def step(self, command: ControlCommand, *, physics_steps: int = 1) -> BackendState: ...

    def close(self) -> None: ...


@runtime_checkable
class SimulationBackend(Protocol):
    def create_session(self, bundle: SceneBundle) -> SimulationBackendSession: ...


def validate_state_layout(description: ModelDescription, state: BackendState) -> BackendState:
    """Reject a corrupt or stale state before it reaches an algorithm."""
    if state.schema_hash != description.schema_hash:
        raise ModelSchemaMismatchError(
            "Backend state model schema does not match the simulation session"
        )
    expected = {
        "joint_positions": len(description.joints),
        "joint_velocities": len(description.joints),
        "actuator_controls": len(description.actuators),
        "actuator_forces": len(description.actuators),
        "body_positions": len(description.bodies),
        "body_quaternions": len(description.bodies),
    }
    for field_name, size in expected.items():
        actual = len(getattr(state, field_name))
        if actual != size:
            raise SimulationBackendError(
                f"Backend state {field_name} expected {size} values; received {actual}"
            )
    return state


def model_schema_hash(
    *,
    body_ids: Sequence[str],
    joint_ids: Sequence[str],
    actuator_ids: Sequence[str],
) -> str:
    payload = json.dumps(
        {
            "contract": "simlab.backend.v1",
            "body_ids": list(body_ids),
            "joint_ids": list(joint_ids),
            "actuator_ids": list(actuator_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
