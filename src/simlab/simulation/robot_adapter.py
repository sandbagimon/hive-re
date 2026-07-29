from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from simlab.simulation.backend import (
    BackendState,
    BoundedArraySpec,
    ControlCommand,
    InvalidControlError,
    ModelDescription,
    ModelSchemaMismatchError,
)


@dataclass(frozen=True, slots=True)
class DirectActuatorAdapter:
    """Map normalized algorithm actions onto named robot actuators."""

    actuator_ids: tuple[str, ...]
    joint_ids: tuple[str, ...] | None = None

    def __init__(
        self,
        actuator_ids: Sequence[str],
        *,
        joint_ids: Sequence[str] | None = None,
    ) -> None:
        object.__setattr__(self, "actuator_ids", tuple(str(item) for item in actuator_ids))
        object.__setattr__(
            self,
            "joint_ids",
            tuple(str(item) for item in joint_ids) if joint_ids is not None else None,
        )
        if not self.actuator_ids or any(not item for item in self.actuator_ids):
            raise ValueError("DirectActuatorAdapter requires non-empty actuator IDs")
        if len(self.actuator_ids) != len(set(self.actuator_ids)):
            raise ValueError("DirectActuatorAdapter actuator IDs must be unique")

    def bind(self, description: ModelDescription) -> BoundDirectActuatorAdapter:
        actuator_index = {item.id: index for index, item in enumerate(description.actuators)}
        unknown_actuators = sorted(set(self.actuator_ids) - set(actuator_index))
        if unknown_actuators:
            raise ValueError(
                "Robot adapter references unknown actuator ID(s): " + ", ".join(unknown_actuators)
            )
        actuator_descriptions = [
            description.actuators[actuator_index[identifier]] for identifier in self.actuator_ids
        ]
        selected_joint_ids = self.joint_ids or tuple(
            item.joint_id for item in actuator_descriptions
        )
        joint_index = {item.id: index for index, item in enumerate(description.joints)}
        unknown_joints = sorted(set(selected_joint_ids) - set(joint_index))
        if unknown_joints:
            raise ValueError(
                "Robot adapter references unknown joint ID(s): " + ", ".join(unknown_joints)
            )
        return BoundDirectActuatorAdapter(
            description=description,
            actuator_indices=tuple(actuator_index[item] for item in self.actuator_ids),
            joint_indices=tuple(joint_index[item] for item in selected_joint_ids),
            actuator_ids=self.actuator_ids,
            joint_ids=tuple(selected_joint_ids),
        )


@dataclass(frozen=True, slots=True)
class BoundDirectActuatorAdapter:
    description: ModelDescription
    actuator_indices: tuple[int, ...]
    joint_indices: tuple[int, ...]
    actuator_ids: tuple[str, ...]
    joint_ids: tuple[str, ...]

    @property
    def action_spec(self) -> BoundedArraySpec:
        size = len(self.actuator_indices)
        return BoundedArraySpec(
            shape=(size,),
            minimum=(-1.0,) * size,
            maximum=(1.0,) * size,
        )

    @property
    def observation_spec(self) -> BoundedArraySpec:
        size = len(self.joint_indices) * 2
        limit = float(np.finfo(np.float32).max)
        return BoundedArraySpec(
            shape=(size,),
            minimum=(-limit,) * size,
            maximum=(limit,) * size,
        )

    def command(self, action: object, state: BackendState) -> ControlCommand:
        self._validate_state(state)
        values = np.asarray(action, dtype=np.float64)
        if values.shape != self.action_spec.shape:
            raise InvalidControlError(
                f"Expected action shape {self.action_spec.shape}; received {values.shape}"
            )
        if not np.all(np.isfinite(values)):
            raise InvalidControlError("Action values must be finite")
        if np.any(values < -1.0) or np.any(values > 1.0):
            raise InvalidControlError("Normalized action values must be in [-1, 1]")
        controls = list(state.actuator_controls)
        for normalized, index in zip(values, self.actuator_indices, strict=True):
            actuator = self.description.actuators[index]
            controls[index] = actuator.lower + (float(normalized) + 1.0) * 0.5 * (
                actuator.upper - actuator.lower
            )
        return ControlCommand(
            schema_hash=self.description.schema_hash,
            values=tuple(controls),
        )

    def observation(self, state: BackendState) -> np.ndarray:
        self._validate_state(state)
        values = [state.joint_positions[index] for index in self.joint_indices]
        values.extend(state.joint_velocities[index] for index in self.joint_indices)
        return np.asarray(values, dtype=np.float32)

    def joint_positions(self, state: BackendState) -> np.ndarray:
        self._validate_state(state)
        return np.asarray(
            [state.joint_positions[index] for index in self.joint_indices],
            dtype=np.float64,
        )

    def _validate_state(self, state: BackendState) -> None:
        if state.schema_hash != self.description.schema_hash:
            raise ModelSchemaMismatchError(
                "Robot adapter received state from a different model schema"
            )
