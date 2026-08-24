from __future__ import annotations

from beefoundrysim.services.physics_validation import PhysicsPreflightReport, run_physics_preflight
from beefoundrysim.services.simulation_session import MuJoCoSimulationSession
from beefoundrysim.simulation.mujoco_descriptor import mujoco_engine_descriptor
from beefoundrysim.simulation.runtime import (
    EngineDescriptor,
    RuntimeSessionRequest,
    SimulationRuntimeSession,
    validate_runtime_request,
)


class MujocoRuntimeBackend:
    """Default live-runtime plugin backed by the existing MuJoCo implementation."""

    @property
    def descriptor(self) -> EngineDescriptor:
        return mujoco_engine_descriptor()

    def preflight(self, request: RuntimeSessionRequest) -> PhysicsPreflightReport:
        validate_runtime_request(self.descriptor, request)
        return run_physics_preflight(request.scene, asset_root=request.project_root)

    def create_session(self, request: RuntimeSessionRequest) -> SimulationRuntimeSession:
        validate_runtime_request(self.descriptor, request)
        return MuJoCoSimulationSession(
            request.scene,
            request.artifact_directory / "scene.xml",
            asset_root=request.project_root,
        )
