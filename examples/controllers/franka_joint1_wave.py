from __future__ import annotations

import math

from beefoundrysim.services.controller_runtime import ControllerAction, ControllerObservation

# Stable joint ID imported from the bundled Franka Panda OpenUSD asset.
PANDA_JOINT1 = "joint_5cff8870396d"
PANDA_JOINT1_LIMITS = (-2.8973, 2.8973)


class FrankaJoint1WaveController:
    """Move panda_joint1 smoothly around the pose where the controller starts."""

    name = "Franka Joint 1 Wave"

    def __init__(self) -> None:
        self._started_at = 0.0
        self._center = 0.0

    def reset(self, observation: ControllerObservation) -> None:
        joint = observation.joints.get(PANDA_JOINT1)
        if joint is None:
            raise ValueError(
                "panda_joint1 was not found; load the bundled Franka Panda asset first"
            )
        self._started_at = observation.time
        self._center = joint.qpos

    def step(self, observation: ControllerObservation) -> ControllerAction:
        elapsed = observation.time - self._started_at
        target = self._center + 0.35 * math.sin(2.0 * math.pi * 0.2 * elapsed)
        lower, upper = PANDA_JOINT1_LIMITS
        target = max(lower, min(upper, target))
        return ControllerAction({PANDA_JOINT1: target})


def create_controller() -> FrankaJoint1WaveController:
    return FrankaJoint1WaveController()
