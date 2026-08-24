from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from beefoundrysim.models.scene import Scene
from beefoundrysim.services.simulation_service import SimulationService
from beefoundrysim.services.simulation_session import SimulationState
from beefoundrysim.simulation.runtime import (
    EngineCapability,
    EngineDescriptor,
    MissingEngineCapabilityError,
    RuntimeSelection,
    RuntimeSessionRequest,
    SolverExtensionDescriptor,
    UnknownRuntimeBackendError,
    UnsupportedSolverCombinationError,
    validate_runtime_request,
)
from beefoundrysim.simulation.runtime_registry import (
    RuntimeBackendRegistry,
    default_runtime_backend_registry,
)
from beefoundrysim.web_application import WebApplication


@dataclass(slots=True)
class FakePreflightReport:
    issues: list[Any] = field(default_factory=list)
    is_valid: bool = True


class FakeRuntimeSession:
    def __init__(self, descriptor: EngineDescriptor, artifact_path: Path) -> None:
        self.engine_descriptor = descriptor
        self.timestep = 0.02
        self.artifact_path = artifact_path
        self.joint_recording = None
        self.closed = False
        self._state = SimulationState(time=0.0, actors=[])

    def state(self) -> SimulationState:
        return self._state

    def step(self, steps: int = 1) -> SimulationState:
        self._state.time += self.timestep * steps
        return self._state

    def reset(self) -> SimulationState:
        self._state.time = 0.0
        return self._state

    def close(self) -> None:
        self.closed = True


class FakeRuntimeBackend:
    descriptor = EngineDescriptor(
        id="newton-test",
        name="Newton Test Adapter",
        version="1.0",
        capabilities=frozenset(
            {EngineCapability.RIGID_BODY, EngineCapability.COLLISION}
        ),
    )

    def __init__(self) -> None:
        self.preflight_requests: list[RuntimeSessionRequest] = []
        self.session_requests: list[RuntimeSessionRequest] = []
        self.session: FakeRuntimeSession | None = None

    def preflight(self, request: RuntimeSessionRequest) -> FakePreflightReport:
        self.preflight_requests.append(request)
        return FakePreflightReport()

    def create_session(self, request: RuntimeSessionRequest) -> FakeRuntimeSession:
        self.session_requests.append(request)
        self.session = FakeRuntimeSession(
            self.descriptor,
            request.artifact_directory / "newton-test.cache",
        )
        return self.session


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _newton_scene() -> Scene:
    return Scene(
        name="Backend independent",
        simulation_config={
            "timestep": 0.02,
            "solvers": {"primary": "newton-test", "extensions": []},
        },
    )


def test_runtime_selection_supports_primary_and_extension_solver_topology() -> None:
    default = RuntimeSelection.from_scene(Scene())
    selected = RuntimeSelection.from_scene(
        Scene(
            simulation_config={
                "solvers": {
                    "primary": "newton",
                    "extensions": ["water-sph", "foam-particles"],
                }
            }
        )
    )

    assert default == RuntimeSelection(primary="mujoco")
    assert selected == RuntimeSelection(
        primary="newton",
        extensions=("water-sph", "foam-particles"),
    )


def test_simulation_service_runs_without_importing_or_accessing_mujoco(tmp_path: Path) -> None:
    backend = FakeRuntimeBackend()
    registry = RuntimeBackendRegistry([backend])
    clock = FakeClock()
    messages: list[str] = []
    service = SimulationService(
        tmp_path,
        messages.append,
        clock=clock,
        runtime_backends=registry,
    )

    report = service.preflight(_newton_scene())
    started = service.start(_newton_scene())
    clock.advance(0.04)
    stepped = service.step_frame()
    session = backend.session
    service.stop()

    assert report.is_valid
    assert started.clock.timestep == pytest.approx(0.02)
    assert stepped is not None and stepped.time == pytest.approx(0.04)
    assert backend.preflight_requests[0].selection.primary == "newton-test"
    assert backend.session_requests[0].project_root == tmp_path
    assert session is not None and session.closed
    assert any("Newton Test Adapter 1.0" in message for message in messages)


def test_web_application_uses_injected_runtime_for_preflight_and_run(tmp_path: Path) -> None:
    backend = FakeRuntimeBackend()
    application = WebApplication(
        tmp_path,
        background_simulation=False,
        runtime_backends=RuntimeBackendRegistry([backend]),
    )
    scene = _newton_scene()

    checked = application.preflight(json.dumps(scene.to_dict()))
    running = application.run_simulation(json.dumps(scene.to_dict()))
    application.close()

    assert checked["ok"] and checked["data"]["valid"]
    assert running["ok"] and running["data"]["state"]["time"] == 0.0
    assert backend.preflight_requests
    assert backend.session_requests


def test_registry_reports_unknown_engine_with_available_backends() -> None:
    registry = RuntimeBackendRegistry([FakeRuntimeBackend()])

    with pytest.raises(
        UnknownRuntimeBackendError,
        match="newton.*Available: newton-test",
    ):
        registry.create_session(
            Scene(simulation_config={"solvers": "newton"}),
            project_root=Path("/project"),
            artifact_directory=Path("/project/exports"),
        )


def test_mujoco_backend_rejects_fluid_requirement_before_loading_engine(
    tmp_path: Path,
) -> None:
    registry = default_runtime_backend_registry(load_plugins=False)
    scene = Scene(
        simulation_config={
            "solvers": "mujoco",
            "required_capabilities": ["fluid"],
        }
    )

    with pytest.raises(MissingEngineCapabilityError, match="fluid"):
        registry.create_session(
            scene,
            project_root=tmp_path,
            artifact_directory=tmp_path / "exports",
        )


def test_mujoco_backend_rejects_unconfigured_extension_solver(tmp_path: Path) -> None:
    registry = default_runtime_backend_registry(load_plugins=False)
    scene = Scene(
        simulation_config={
            "solvers": {"primary": "mujoco", "extensions": ["water-sph"]}
        }
    )

    with pytest.raises(UnsupportedSolverCombinationError, match="water-sph"):
        registry.create_session(
            scene,
            project_root=tmp_path,
            artifact_directory=tmp_path / "exports",
        )


def test_extension_solver_contributes_capabilities_to_composed_runtime(
    tmp_path: Path,
) -> None:
    descriptor = EngineDescriptor(
        id="newton",
        name="Newton",
        version="1.0",
        capabilities=frozenset(
            {EngineCapability.RIGID_BODY, EngineCapability.COLLISION}
        ),
        extensions=(
            SolverExtensionDescriptor(
                id="water-sph",
                capabilities=frozenset(
                    {EngineCapability.FLUID, EngineCapability.PARTICLE}
                ),
            ),
        ),
    )
    scene = Scene(
        simulation_config={
            "solvers": {"primary": "newton", "extensions": ["water-sph"]},
            "required_capabilities": ["fluid"],
        }
    )
    request = RuntimeSessionRequest(
        scene=scene,
        project_root=tmp_path,
        artifact_directory=tmp_path / "exports",
        selection=RuntimeSelection.from_scene(scene),
    )

    validate_runtime_request(descriptor, request)

    assert descriptor.effective_capabilities(request.selection).issuperset(
        {EngineCapability.RIGID_BODY, EngineCapability.FLUID}
    )
