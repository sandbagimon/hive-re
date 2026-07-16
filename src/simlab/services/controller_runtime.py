from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol


@dataclass(frozen=True, slots=True)
class JointObservation:
    qpos: float
    qvel: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.qpos) or not math.isfinite(self.qvel):
            raise ValueError("Joint observation values must be finite")


@dataclass(frozen=True, slots=True)
class ActuatorObservation:
    ctrl: float
    force: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.ctrl) or not math.isfinite(self.force):
            raise ValueError("Actuator observation values must be finite")


@dataclass(frozen=True, slots=True)
class ControllerObservation:
    time: float
    timestep: float
    joints: Mapping[str, JointObservation]
    actuators: Mapping[str, ActuatorObservation]

    def __post_init__(self) -> None:
        if not math.isfinite(self.time) or self.time < 0:
            raise ValueError("Controller observation time must be finite and >= 0")
        if not math.isfinite(self.timestep) or self.timestep <= 0:
            raise ValueError("Controller observation timestep must be finite and > 0")
        object.__setattr__(self, "joints", MappingProxyType(dict(self.joints)))
        object.__setattr__(self, "actuators", MappingProxyType(dict(self.actuators)))


@dataclass(frozen=True, slots=True)
class ControllerAction:
    position_targets: Mapping[str, float]

    def __post_init__(self) -> None:
        targets = {str(joint_id): float(value) for joint_id, value in self.position_targets.items()}
        if any(not joint_id for joint_id in targets):
            raise ValueError("Controller action joint IDs must not be empty")
        if any(not math.isfinite(value) for value in targets.values()):
            raise ValueError("Controller position targets must be finite")
        object.__setattr__(self, "position_targets", MappingProxyType(targets))


class StepController(Protocol):
    def reset(self, observation: ControllerObservation) -> None: ...

    def step(self, observation: ControllerObservation) -> ControllerAction | None: ...


@dataclass(frozen=True, slots=True)
class ControllerRunnerState:
    status: str
    name: str | None
    message: str | None
    step_count: int
    last_duration: float | None
    deadline: float | None


Clock = Callable[[], float]


class ControllerRunner:
    """Run user controllers behind an immutable, failure-contained boundary."""

    def __init__(
        self,
        *,
        deadline: float | None = None,
        clock: Clock = time.perf_counter,
    ) -> None:
        if deadline is not None and (not math.isfinite(deadline) or deadline <= 0):
            raise ValueError("Controller deadline must be finite and > 0")
        self.deadline = deadline
        self.clock = clock
        self._controller: StepController | None = None
        self._name: str | None = None
        self._status = "disabled"
        self._message: str | None = None
        self._step_count = 0
        self._last_duration: float | None = None

    @property
    def enabled(self) -> bool:
        return self._controller is not None and self._status != "fault"

    @property
    def state(self) -> ControllerRunnerState:
        return ControllerRunnerState(
            status=self._status,
            name=self._name,
            message=self._message,
            step_count=self._step_count,
            last_duration=self._last_duration,
            deadline=self.deadline,
        )

    def attach(self, controller: StepController, *, name: str | None = None) -> None:
        if not callable(getattr(controller, "reset", None)) or not callable(
            getattr(controller, "step", None)
        ):
            raise TypeError("Controller must define reset() and step()")
        self._controller = controller
        self._name = name or type(controller).__name__
        self._status = "ready"
        self._message = None
        self._step_count = 0
        self._last_duration = None

    def detach(self) -> None:
        self._controller = None
        self._name = None
        self._status = "disabled"
        self._message = None
        self._step_count = 0
        self._last_duration = None

    def reset(self, observation: ControllerObservation) -> bool:
        controller = self._controller
        if controller is None or self._status == "fault":
            return False
        started = self.clock()
        try:
            controller.reset(observation)
        except Exception as exc:
            self._fault(f"Controller reset failed: {exc}")
            return False
        duration = max(0.0, self.clock() - started)
        self._last_duration = duration
        if self._deadline_exceeded(duration):
            return False
        self._status = "ready"
        self._message = None
        self._step_count = 0
        return True

    def step(self, observation: ControllerObservation) -> ControllerAction | None:
        controller = self._controller
        if controller is None or self._status == "fault":
            return None
        started = self.clock()
        try:
            action = controller.step(observation)
            if action is not None and not isinstance(action, ControllerAction):
                raise TypeError("Controller step must return ControllerAction or None")
        except Exception as exc:
            self._fault(f"Controller step failed: {exc}")
            return None
        duration = max(0.0, self.clock() - started)
        self._last_duration = duration
        if self._deadline_exceeded(duration):
            return None
        self._step_count += 1
        self._status = "active"
        self._message = None
        return action

    def _deadline_exceeded(self, duration: float) -> bool:
        if self.deadline is None or duration <= self.deadline:
            return False
        self._fault(
            f"Controller deadline exceeded: {duration:.6f}s > {self.deadline:.6f}s"
        )
        return True

    def _fault(self, message: str) -> None:
        self._status = "fault"
        self._message = message

