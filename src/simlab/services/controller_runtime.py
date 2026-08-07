from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
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
class BodyObservation:
    position: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]
    linear_velocity: tuple[float, float, float]
    angular_velocity: tuple[float, float, float]

    def __post_init__(self) -> None:
        if (
            len(self.position) != 3
            or len(self.quaternion) != 4
            or len(self.linear_velocity) != 3
            or len(self.angular_velocity) != 3
        ):
            raise ValueError("Body observation vectors have invalid dimensions")
        values = (
            *self.position,
            *self.quaternion,
            *self.linear_velocity,
            *self.angular_velocity,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Body observation values must be finite")


@dataclass(frozen=True, slots=True)
class AttachmentObservation:
    active: bool
    requested_active: bool
    eligible: bool
    contact: bool
    distance: float
    relative_speed: float

    def __post_init__(self) -> None:
        if any(
            not math.isfinite(value) or value < 0
            for value in (self.distance, self.relative_speed)
        ):
            raise ValueError("Attachment observation distance and speed must be finite and >= 0")


@dataclass(frozen=True, slots=True)
class RangefinderObservation:
    distance: float
    max_distance: float
    hit: bool

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.distance)
            or not math.isfinite(self.max_distance)
            or self.distance < 0
            or self.max_distance <= 0
            or self.distance > self.max_distance
        ):
            raise ValueError("Rangefinder observation distance bounds are invalid")


@dataclass(frozen=True, slots=True)
class ControllerObservation:
    time: float
    timestep: float
    joints: Mapping[str, JointObservation]
    actuators: Mapping[str, ActuatorObservation]
    bodies: Mapping[str, BodyObservation] = field(default_factory=dict)
    attachments: Mapping[str, AttachmentObservation] = field(default_factory=dict)
    rangefinders: Mapping[str, RangefinderObservation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.time) or self.time < 0:
            raise ValueError("Controller observation time must be finite and >= 0")
        if not math.isfinite(self.timestep) or self.timestep <= 0:
            raise ValueError("Controller observation timestep must be finite and > 0")
        object.__setattr__(self, "joints", MappingProxyType(dict(self.joints)))
        object.__setattr__(self, "actuators", MappingProxyType(dict(self.actuators)))
        object.__setattr__(self, "bodies", MappingProxyType(dict(self.bodies)))
        object.__setattr__(self, "attachments", MappingProxyType(dict(self.attachments)))
        object.__setattr__(self, "rangefinders", MappingProxyType(dict(self.rangefinders)))


@dataclass(frozen=True, slots=True)
class ControllerAction:
    position_targets: Mapping[str, float] = field(default_factory=dict)
    actuator_controls: Mapping[str, float] = field(default_factory=dict)
    attachment_commands: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        targets = {str(joint_id): float(value) for joint_id, value in self.position_targets.items()}
        if any(not joint_id for joint_id in targets):
            raise ValueError("Controller action joint IDs must not be empty")
        if any(not math.isfinite(value) for value in targets.values()):
            raise ValueError("Controller position targets must be finite")
        controls = {
            str(actuator_id): float(value)
            for actuator_id, value in self.actuator_controls.items()
        }
        if any(not actuator_id for actuator_id in controls):
            raise ValueError("Controller action actuator IDs must not be empty")
        if any(not math.isfinite(value) for value in controls.values()):
            raise ValueError("Controller actuator controls must be finite")
        commands: dict[str, bool] = {}
        for attachment_id, active in self.attachment_commands.items():
            identifier = str(attachment_id)
            if not identifier:
                raise ValueError("Controller attachment IDs must not be empty")
            if not isinstance(active, bool):
                raise ValueError(
                    f"Controller attachment command must be boolean: {identifier}"
                )
            commands[identifier] = active
        object.__setattr__(self, "position_targets", MappingProxyType(targets))
        object.__setattr__(self, "actuator_controls", MappingProxyType(controls))
        object.__setattr__(self, "attachment_commands", MappingProxyType(commands))


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
    reset_deadline: float | None


Clock = Callable[[], float]


class ControllerRunner:
    """Run user controllers behind an immutable, failure-contained boundary."""

    def __init__(
        self,
        *,
        deadline: float | None = None,
        reset_deadline: float | None = None,
        clock: Clock = time.perf_counter,
    ) -> None:
        if deadline is not None and (not math.isfinite(deadline) or deadline <= 0):
            raise ValueError("Controller deadline must be finite and > 0")
        if reset_deadline is not None and (
            not math.isfinite(reset_deadline) or reset_deadline <= 0
        ):
            raise ValueError("Controller reset deadline must be finite and > 0")
        self.deadline = deadline
        self.reset_deadline = reset_deadline
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
    def attached(self) -> bool:
        return self._controller is not None

    @property
    def state(self) -> ControllerRunnerState:
        return ControllerRunnerState(
            status=self._status,
            name=self._name,
            message=self._message,
            step_count=self._step_count,
            last_duration=self._last_duration,
            deadline=self.deadline,
            reset_deadline=self.reset_deadline,
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

    def fail(self, message: str) -> None:
        if self._controller is not None:
            self._fault(message)

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
        if self._deadline_exceeded(
            duration,
            deadline=self.reset_deadline,
            label="Controller reset deadline",
        ):
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
        if self._deadline_exceeded(
            duration,
            deadline=self.deadline,
            label="Controller deadline",
        ):
            return None
        self._step_count += 1
        self._status = "active"
        self._message = None
        return action

    def _deadline_exceeded(
        self,
        duration: float,
        *,
        deadline: float | None,
        label: str,
    ) -> bool:
        if deadline is None or duration <= deadline:
            return False
        self._fault(f"{label} exceeded: {duration:.6f}s > {deadline:.6f}s")
        return True

    def _fault(self, message: str) -> None:
        self._status = "fault"
        self._message = message
