from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from beefoundrysim.simulation.backend import (
    BackendState,
    BoundedArraySpec,
    ControlCommand,
    ModelDescription,
)
from beefoundrysim.simulation.robot_adapter import (
    BoundDirectActuatorAdapter,
    DirectActuatorAdapter,
)


@dataclass(frozen=True, slots=True)
class TaskEvaluation:
    observation: np.ndarray
    reward: float
    terminated: bool
    truncated: bool
    info: Mapping[str, Any]


class BoundEnvironmentTask(Protocol):
    @property
    def action_spec(self) -> BoundedArraySpec: ...

    @property
    def observation_spec(self) -> BoundedArraySpec: ...

    def reset(
        self, state: BackendState, rng: np.random.Generator
    ) -> tuple[np.ndarray, Mapping[str, Any]]: ...

    def command(self, action: object, state: BackendState) -> ControlCommand: ...

    def evaluate(self, state: BackendState, *, episode_step: int) -> TaskEvaluation: ...


class EnvironmentTask(Protocol):
    def bind(self, description: ModelDescription) -> BoundEnvironmentTask: ...


@dataclass(frozen=True, slots=True)
class JointTargetTask:
    """A minimal trainable task kept entirely outside the physics backend."""

    robot: DirectActuatorAdapter
    target_positions: tuple[float, ...]
    random_target_ranges: tuple[tuple[float, float], ...] | None = None
    success_tolerance: float = 0.02
    max_episode_steps: int = 500
    terminate_on_success: bool = True

    def __post_init__(self) -> None:
        if not self.target_positions:
            raise ValueError("JointTargetTask requires at least one target position")
        if any(not math.isfinite(value) for value in self.target_positions):
            raise ValueError("Joint target positions must be finite")
        if self.random_target_ranges is not None:
            if len(self.random_target_ranges) != len(self.target_positions):
                raise ValueError("Random target ranges must match target position count")
            for lower, upper in self.random_target_ranges:
                if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
                    raise ValueError("Random target ranges must be finite and ordered")
        if not math.isfinite(self.success_tolerance) or self.success_tolerance <= 0:
            raise ValueError("success_tolerance must be finite and > 0")
        if self.max_episode_steps < 1:
            raise ValueError("max_episode_steps must be >= 1")

    def bind(self, description: ModelDescription) -> BoundJointTargetTask:
        robot = self.robot.bind(description)
        if len(self.target_positions) != len(robot.joint_indices):
            raise ValueError("Joint target count must match the robot adapter observation joints")
        return BoundJointTargetTask(
            robot=robot,
            target_positions=np.asarray(self.target_positions, dtype=np.float64),
            random_target_ranges=(
                np.asarray(self.random_target_ranges, dtype=np.float64)
                if self.random_target_ranges is not None
                else None
            ),
            success_tolerance=self.success_tolerance,
            max_episode_steps=self.max_episode_steps,
            terminate_on_success=self.terminate_on_success,
        )


@dataclass(slots=True)
class BoundJointTargetTask:
    robot: BoundDirectActuatorAdapter
    target_positions: np.ndarray
    random_target_ranges: np.ndarray | None
    success_tolerance: float
    max_episode_steps: int
    terminate_on_success: bool

    @property
    def action_spec(self) -> BoundedArraySpec:
        return self.robot.action_spec

    @property
    def observation_spec(self) -> BoundedArraySpec:
        robot_size = self.robot.observation_spec.shape[0]
        target_size = len(self.target_positions)
        size = robot_size + target_size
        limit = float(np.finfo(np.float32).max)
        return BoundedArraySpec(
            shape=(size,),
            minimum=(-limit,) * size,
            maximum=(limit,) * size,
        )

    def reset(
        self, state: BackendState, rng: np.random.Generator
    ) -> tuple[np.ndarray, Mapping[str, Any]]:
        if self.random_target_ranges is not None:
            self.target_positions = rng.uniform(
                self.random_target_ranges[:, 0],
                self.random_target_ranges[:, 1],
            )
        return self._observation(state), self._info(state)

    def command(self, action: object, state: BackendState) -> ControlCommand:
        return self.robot.command(action, state)

    def evaluate(self, state: BackendState, *, episode_step: int) -> TaskEvaluation:
        error = self.robot.joint_positions(state) - self.target_positions
        error_norm = float(np.linalg.norm(error))
        success = error_norm <= self.success_tolerance
        return TaskEvaluation(
            observation=self._observation(state),
            reward=-error_norm,
            terminated=bool(success and self.terminate_on_success),
            truncated=episode_step >= self.max_episode_steps,
            info=self._info(state),
        )

    def _observation(self, state: BackendState) -> np.ndarray:
        return np.concatenate(
            (
                self.robot.observation(state),
                self.target_positions.astype(np.float32, copy=False),
            ),
            dtype=np.float32,
        )

    def _info(self, state: BackendState) -> Mapping[str, Any]:
        error = self.robot.joint_positions(state) - self.target_positions
        error_norm = float(np.linalg.norm(error))
        return {
            "target_positions": self.target_positions.astype(float).tolist(),
            "joint_ids": list(self.robot.joint_ids),
            "error_norm": error_norm,
            "is_success": error_norm <= self.success_tolerance,
            "simulation_time": state.time,
            "physics_step": state.step_index,
        }
