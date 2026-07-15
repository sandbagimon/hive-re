from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from simlab.models.scene import Scene
from simlab.services.simulation_session import MuJoCoSimulationSession, SimulationState

ConsoleCallback = Callable[[str], None]


class SimulationService:
    """Manage an in-process MuJoCo session for live viewport state sync."""

    def __init__(self, project_root: Path, console: ConsoleCallback | None = None) -> None:
        self.project_root = project_root
        self.console = console or print
        self.session: MuJoCoSimulationSession | None = None
        self.running = False

    def is_running(self) -> bool:
        return self.running

    def start(self, scene: Scene) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        self.running = True
        self.console("Simulation running.")
        return self.session.state()

    def pause(self) -> None:
        if not self.session:
            self.console("No simulation is loaded.")
            return
        self.running = False
        self.console("Simulation paused.")

    def step_once(self, scene: Scene) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        self.running = False
        state = self.session.step()
        self.console(f"Simulation step: t={state.time:.3f}")
        return state

    def step_frame(self) -> SimulationState | None:
        if not self.running or self.session is None:
            return None
        return self.session.step()

    def set_joint_position_targets(
        self, scene: Scene, targets: dict[str, float]
    ) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        state = self.session.set_joint_position_targets(targets)
        self.console(f"Updated {len(targets)} joint target(s).")
        return state

    def reset(self) -> None:
        if self.session is None:
            self.console("No simulation is loaded.")
            return
        self.session.reset()
        self.session = None
        self.running = False
        self.console("Simulation reset.")

    def _create_session(self, scene: Scene) -> MuJoCoSimulationSession:
        export_path = self.project_root / "exports" / "scene.xml"
        return MuJoCoSimulationSession(scene, export_path, asset_root=self.project_root)
