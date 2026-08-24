from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from beefoundrysim.models.recording import JointStateRecording
    from beefoundrysim.models.scene import Scene
    from beefoundrysim.models.trajectory import JointTrajectory
    from beefoundrysim.services.controller_runtime import StepController
    from beefoundrysim.services.simulation_session import SimulationState


class RuntimeBackendError(RuntimeError):
    """Base error raised by a live simulation runtime backend."""


class UnknownRuntimeBackendError(RuntimeBackendError):
    """Raised when a scene selects a runtime backend that is not registered."""


class UnsupportedSolverCombinationError(RuntimeBackendError):
    """Raised when a primary backend cannot compose the requested extension solvers."""


class MissingEngineCapabilityError(RuntimeBackendError):
    """Raised when an engine cannot provide a capability required by a scene."""


class EngineCapability(StrEnum):
    """Physics primitives exposed by a runtime backend.

    Application features such as trajectories and recording deliberately do not appear here;
    every ``SimulationRuntimeSession`` must provide those stable application-level operations.
    """

    RIGID_BODY = "rigid_body"
    ARTICULATION = "articulation"
    COLLISION = "collision"
    CONSTRAINT = "constraint"
    EXTERNAL_FORCE = "external_force"
    RAY_QUERY = "ray_query"
    KINEMATIC_ACTOR = "kinematic_actor"
    FLUID = "fluid"
    PARTICLE = "particle"
    DEFORMABLE_BODY = "deformable_body"
    DIFFERENTIABLE = "differentiable"


@dataclass(frozen=True, slots=True)
class SolverExtensionDescriptor:
    """Capabilities added when a primary adapter composes one extension solver."""

    id: str
    capabilities: frozenset[EngineCapability]

    def __post_init__(self) -> None:
        _validate_backend_id(self.id, "Extension engine id")


@dataclass(frozen=True, slots=True)
class EngineDescriptor:
    """Discoverable identity and capabilities of one physics runtime adapter."""

    id: str
    name: str
    version: str
    capabilities: frozenset[EngineCapability]
    extensions: tuple[SolverExtensionDescriptor, ...] = ()

    def __post_init__(self) -> None:
        _validate_backend_id(self.id, "Engine id")
        if not self.name.strip():
            raise ValueError("Engine name must not be empty")
        if not self.version.strip():
            raise ValueError("Engine version must not be empty")
        extension_ids = [extension.id for extension in self.extensions]
        if len(extension_ids) != len(set(extension_ids)):
            raise ValueError("Engine extension ids must be unique")

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset(extension.id for extension in self.extensions)

    def effective_capabilities(
        self,
        selection: RuntimeSelection,
    ) -> frozenset[EngineCapability]:
        result = set(self.capabilities)
        selected = set(selection.extensions)
        for extension in self.extensions:
            if extension.id in selected:
                result.update(extension.capabilities)
        return frozenset(result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "capabilities": sorted(item.value for item in self.capabilities),
            "extensions": [
                {
                    "id": extension.id,
                    "capabilities": sorted(
                        capability.value for capability in extension.capabilities
                    ),
                }
                for extension in self.extensions
            ],
        }


@dataclass(frozen=True, slots=True)
class RuntimeSelection:
    """Scene-owned solver topology, independent of process transport.

    ``primary`` advances the authoritative clock and rigid/articulation state. ``extensions``
    reserve an ordered composition point for fluid, particle, deformable, or other coupled
    solvers. A backend must reject combinations it cannot couple instead of silently ignoring
    them.
    """

    primary: str = "mujoco"
    extensions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_backend_id(self.primary, "Primary engine id")
        for extension in self.extensions:
            _validate_backend_id(extension, "Extension engine id")
        if len(self.extensions) != len(set(self.extensions)):
            raise ValueError("Extension engine ids must be unique")
        if self.primary in self.extensions:
            raise ValueError("Primary engine cannot also be an extension engine")

    @classmethod
    def from_scene(cls, scene: Scene) -> RuntimeSelection:
        raw = scene.simulation_config.get("solvers")
        if raw is None:
            legacy = scene.simulation_config.get("physics_engine", "mujoco")
            if not isinstance(legacy, str):
                raise ValueError("simulation_config.physics_engine must be a string")
            return cls(primary=legacy)
        if isinstance(raw, str):
            return cls(primary=raw)
        if not isinstance(raw, Mapping):
            raise ValueError("simulation_config.solvers must be a string or object")
        primary = raw.get("primary", "mujoco")
        extensions = raw.get("extensions", [])
        if not isinstance(primary, str):
            raise ValueError("simulation_config.solvers.primary must be a string")
        if not isinstance(extensions, list) or not all(
            isinstance(item, str) for item in extensions
        ):
            raise ValueError("simulation_config.solvers.extensions must be an array of strings")
        return cls(primary=primary, extensions=tuple(extensions))


@dataclass(frozen=True, slots=True)
class RuntimeSessionRequest:
    """All deployment context needed to create or validate a live runtime session."""

    scene: Scene
    project_root: Path
    artifact_directory: Path
    selection: RuntimeSelection


class RuntimePreflightReport(Protocol):
    """Minimal application-facing result shared by engine-specific validators."""

    @property
    def issues(self) -> Sequence[RuntimeValidationIssue]: ...

    @property
    def is_valid(self) -> bool: ...


class RuntimeValidationIssue(Protocol):
    """Transport-neutral validation issue published by any engine adapter."""

    @property
    def severity(self) -> Literal["error", "warning"]: ...

    @property
    def code(self) -> str: ...

    @property
    def message(self) -> str: ...

    @property
    def actor_id(self) -> str | None: ...

    @property
    def actor_name(self) -> str | None: ...

    @property
    def field(self) -> str | None: ...


class SimulationRuntimeSession(Protocol):
    """Complete live-editor contract implemented by every physics runtime adapter."""

    @property
    def engine_descriptor(self) -> EngineDescriptor: ...

    @property
    def timestep(self) -> float: ...

    @property
    def artifact_path(self) -> Path | None: ...

    @property
    def joint_recording(self) -> JointStateRecording | None: ...

    def state(self) -> SimulationState: ...

    def step(self, steps: int = 1) -> SimulationState: ...

    def reset(self) -> SimulationState: ...

    def close(self) -> None: ...

    def attach_controller(
        self,
        controller: StepController,
        *,
        name: str | None = None,
    ) -> SimulationState: ...

    def detach_controller(self) -> SimulationState: ...

    def set_joint_position_targets(self, targets: dict[str, float]) -> SimulationState: ...

    def set_actuator_controls(self, controls: dict[str, float]) -> SimulationState: ...

    def set_attachment_commands(self, commands: dict[str, bool]) -> SimulationState: ...

    def load_joint_trajectory(self, trajectory: JointTrajectory) -> SimulationState: ...

    def play_trajectory(self) -> SimulationState: ...

    def pause_trajectory(self) -> SimulationState: ...

    def stop_trajectory(self) -> SimulationState: ...

    def start_joint_recording(
        self,
        *,
        name: str,
        joint_ids: list[str] | None = None,
        actuator_ids: list[str] | None = None,
        sensor_ids: list[str] | None = None,
    ) -> SimulationState: ...

    def stop_joint_recording(self) -> tuple[SimulationState, JointStateRecording]: ...


class SimulationRuntimeBackend(Protocol):
    """Factory/validator plugin for one primary live simulation engine."""

    @property
    def descriptor(self) -> EngineDescriptor: ...

    def preflight(self, request: RuntimeSessionRequest) -> RuntimePreflightReport: ...

    def create_session(self, request: RuntimeSessionRequest) -> SimulationRuntimeSession: ...


def required_engine_capabilities(scene: Scene) -> frozenset[EngineCapability]:
    """Infer the physical primitives a scene needs before an adapter loads it."""

    required: set[EngineCapability] = {EngineCapability.RIGID_BODY}
    if scene.actors:
        required.add(EngineCapability.COLLISION)
    if scene.robotics is not None and scene.robotics.articulations:
        required.add(EngineCapability.ARTICULATION)
        sensor_types = {
            sensor.sensor_type
            for articulation in scene.robotics.articulations
            for sensor in articulation.sensors
        }
        if "contact" in sensor_types:
            required.add(EngineCapability.COLLISION)
        if "rangefinder" in sensor_types:
            required.add(EngineCapability.RAY_QUERY)
    if scene.attachments:
        required.update({EngineCapability.COLLISION, EngineCapability.CONSTRAINT})
    if any(isinstance(actor.properties.get("propulsion"), Mapping) for actor in scene.actors):
        required.add(EngineCapability.EXTERNAL_FORCE)
    if scene.simulation_config.get("dynamic_events"):
        required.add(EngineCapability.KINEMATIC_ACTOR)

    explicit = scene.simulation_config.get("required_capabilities", [])
    if not isinstance(explicit, list) or not all(isinstance(item, str) for item in explicit):
        raise ValueError("simulation_config.required_capabilities must be an array of strings")
    for value in explicit:
        try:
            required.add(EngineCapability(value))
        except ValueError as exc:
            supported = ", ".join(item.value for item in EngineCapability)
            raise ValueError(
                f"Unknown required engine capability '{value}'. Supported values: {supported}"
            ) from exc
    return frozenset(required)


def validate_runtime_request(
    descriptor: EngineDescriptor,
    request: RuntimeSessionRequest,
) -> None:
    """Apply the common selection and capability checks used by runtime adapters."""

    if request.selection.primary != descriptor.id:
        raise RuntimeBackendError(
            f"Runtime request selected '{request.selection.primary}', not '{descriptor.id}'"
        )
    unsupported_extensions = set(request.selection.extensions) - set(
        descriptor.supported_extensions
    )
    if unsupported_extensions:
        values = ", ".join(sorted(unsupported_extensions))
        raise UnsupportedSolverCombinationError(
            f"Engine '{descriptor.id}' cannot compose extension solver(s): {values}"
        )
    missing = required_engine_capabilities(request.scene) - descriptor.effective_capabilities(
        request.selection
    )
    if missing:
        values = ", ".join(sorted(item.value for item in missing))
        raise MissingEngineCapabilityError(
            f"Engine '{descriptor.id}' is missing required capability/capabilities: {values}"
        )


def _validate_backend_id(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", value):
        raise ValueError(
            f"{label} must start with a lowercase letter or digit and contain only "
            "lowercase letters, digits, '.', '_' or '-'"
        )
