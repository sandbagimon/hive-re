from __future__ import annotations

from collections.abc import Iterable
from importlib import metadata
from pathlib import Path
from typing import cast

from simlab.models.scene import Scene
from simlab.simulation.runtime import (
    EngineDescriptor,
    RuntimePreflightReport,
    RuntimeSelection,
    RuntimeSessionRequest,
    SimulationRuntimeBackend,
    SimulationRuntimeSession,
    UnknownRuntimeBackendError,
)

RUNTIME_BACKEND_ENTRY_POINT = "simlab.runtime_backends"


class RuntimeBackendRegistry:
    """Application composition root for built-in and third-party physics runtimes."""

    def __init__(self, backends: Iterable[SimulationRuntimeBackend] = ()) -> None:
        self._backends: dict[str, SimulationRuntimeBackend] = {}
        for backend in backends:
            self.register(backend)

    def register(
        self,
        backend: SimulationRuntimeBackend,
        *,
        replace: bool = False,
    ) -> None:
        identifier = backend.descriptor.id
        if identifier in self._backends and not replace:
            raise ValueError(f"Runtime backend is already registered: {identifier}")
        self._backends[identifier] = backend

    @property
    def descriptors(self) -> tuple[EngineDescriptor, ...]:
        return tuple(
            self._backends[key].descriptor for key in sorted(self._backends)
        )

    def backend_for(self, selection: RuntimeSelection) -> SimulationRuntimeBackend:
        try:
            return self._backends[selection.primary]
        except KeyError as exc:
            available = ", ".join(sorted(self._backends)) or "none"
            raise UnknownRuntimeBackendError(
                f"Runtime backend '{selection.primary}' is not registered. Available: {available}"
            ) from exc

    def preflight(
        self,
        scene: Scene,
        *,
        project_root: Path,
        artifact_directory: Path,
    ) -> RuntimePreflightReport:
        request = self._request(scene, project_root, artifact_directory)
        return self.backend_for(request.selection).preflight(request)

    def create_session(
        self,
        scene: Scene,
        *,
        project_root: Path,
        artifact_directory: Path,
    ) -> SimulationRuntimeSession:
        request = self._request(scene, project_root, artifact_directory)
        return self.backend_for(request.selection).create_session(request)

    @staticmethod
    def _request(
        scene: Scene,
        project_root: Path,
        artifact_directory: Path,
    ) -> RuntimeSessionRequest:
        return RuntimeSessionRequest(
            scene=scene,
            project_root=project_root,
            artifact_directory=artifact_directory,
            selection=RuntimeSelection.from_scene(scene),
        )


def default_runtime_backend_registry(
    *,
    load_plugins: bool = True,
) -> RuntimeBackendRegistry:
    """Build the default registry without importing an engine in application services."""

    from simlab.simulation.mujoco_runtime import MujocoRuntimeBackend

    registry = RuntimeBackendRegistry([MujocoRuntimeBackend()])
    if not load_plugins:
        return registry

    entry_points = metadata.entry_points()
    selected = entry_points.select(group=RUNTIME_BACKEND_ENTRY_POINT)
    for entry_point in selected:
        loaded = entry_point.load()
        candidate = loaded() if isinstance(loaded, type) else loaded
        if callable(candidate) and not hasattr(candidate, "descriptor"):
            candidate = candidate()
        registry.register(cast(SimulationRuntimeBackend, candidate))
    return registry
