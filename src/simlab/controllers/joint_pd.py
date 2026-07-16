from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from simlab.services.controller_runtime import ControllerAction, ControllerObservation


@dataclass(frozen=True, slots=True)
class JointPdConfig:
    target: float
    kp: float = 0.2
    kd: float = 0.01
    max_delta: float = 0.05
    tolerance: float = 1e-4

    def __post_init__(self) -> None:
        values = (self.target, self.kp, self.kd, self.max_delta, self.tolerance)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Joint PD configuration values must be finite")
        if self.kp <= 0:
            raise ValueError("Joint PD kp must be > 0")
        if self.kd < 0:
            raise ValueError("Joint PD kd must be >= 0")
        if self.max_delta <= 0:
            raise ValueError("Joint PD max_delta must be > 0")
        if self.tolerance < 0:
            raise ValueError("Joint PD tolerance must be >= 0")


class JointPositionPdController:
    """Shape position-drive targets with a bounded joint-space PD outer loop."""

    def __init__(
        self,
        joints: Mapping[str, JointPdConfig],
        *,
        name: str = "Joint PD Controller",
    ) -> None:
        if not joints:
            raise ValueError("Joint PD controller requires at least one joint")
        if any(not joint_id for joint_id in joints):
            raise ValueError("Joint PD joint IDs must not be empty")
        self.name = name
        self._joints = dict(joints)
        self.last_reset_time: float | None = None

    @property
    def configs(self) -> Mapping[str, JointPdConfig]:
        return MappingProxyType(self._joints)

    def set_target(self, joint_id: str, target: float) -> None:
        config = self._joints.get(joint_id)
        if config is None:
            raise ValueError(f"Joint PD target references unknown joint: {joint_id}")
        value = float(target)
        if not math.isfinite(value):
            raise ValueError(f"Joint PD target must be finite: {joint_id}")
        self._joints[joint_id] = replace(config, target=value)

    def set_targets(self, targets: Mapping[str, float]) -> None:
        updates: dict[str, JointPdConfig] = {}
        for joint_id, target in targets.items():
            config = self._joints.get(joint_id)
            if config is None:
                raise ValueError(f"Joint PD target references unknown joint: {joint_id}")
            value = float(target)
            if not math.isfinite(value):
                raise ValueError(f"Joint PD target must be finite: {joint_id}")
            updates[joint_id] = replace(config, target=value)
        self._joints.update(updates)

    def reset(self, observation: ControllerObservation) -> None:
        self._validate_observation(observation)
        self.last_reset_time = observation.time

    def step(self, observation: ControllerObservation) -> ControllerAction:
        self._validate_observation(observation)
        targets: dict[str, float] = {}
        for joint_id, config in self._joints.items():
            state = observation.joints[joint_id]
            error = config.target - state.qpos
            if abs(error) <= config.tolerance and abs(state.qvel) <= config.tolerance:
                targets[joint_id] = config.target
                continue
            correction = config.kp * error - config.kd * state.qvel
            delta = max(-config.max_delta, min(config.max_delta, correction))
            targets[joint_id] = state.qpos + delta
        return ControllerAction(targets)

    def _validate_observation(self, observation: ControllerObservation) -> None:
        missing = sorted(set(self._joints) - set(observation.joints))
        if missing:
            raise ValueError(
                "Joint PD observation is missing configured joints: " + ", ".join(missing)
            )
