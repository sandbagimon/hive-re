from __future__ import annotations

import math
import time
from collections.abc import Callable
from pathlib import Path

from simlab.models.scene import Scene
from simlab.services.simulation_session import MuJoCoSimulationSession, SimulationState

ConsoleCallback = Callable[[str], None]
Clock = Callable[[], float]


class SimulationService:
    """Manage an in-process MuJoCo session for live viewport state sync."""

    def __init__(
        self,
        project_root: Path,
        console: ConsoleCallback | None = None,
        *,
        clock: Clock = time.monotonic,
        max_catch_up_steps: int = 8,
    ) -> None:
        if max_catch_up_steps < 1:
            raise ValueError("max_catch_up_steps must be >= 1")
        self.project_root = project_root
        self.console = console or print
        self.clock = clock
        self.default_max_catch_up_steps = max_catch_up_steps
        self.max_catch_up_steps = max_catch_up_steps
        self.session: MuJoCoSimulationSession | None = None
        self.running = False
        self._last_wall_time: float | None = None
        self._time_accumulator = 0.0

    def is_running(self) -> bool:
        return self.running

    def start(self, scene: Scene) -> SimulationState:
        self.max_catch_up_steps = self._read_max_catch_up_steps(scene)
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        self.running = True
        self._last_wall_time = self.clock()
        self._time_accumulator = 0.0
        self.console("Simulation running.")
        return self.session.state()

    def pause(self) -> None:
        if not self.session:
            self.console("No simulation is loaded.")
            return
        self.running = False
        self._last_wall_time = None
        self._time_accumulator = 0.0
        self.console("Simulation paused.")

    def step_once(self, scene: Scene) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        self.running = False
        self._last_wall_time = None
        self._time_accumulator = 0.0
        state = self.session.step()
        self.console(f"Simulation step: t={state.time:.3f}")
        return state

    def step_frame(self) -> SimulationState | None:
        if not self.running or self.session is None:
            return None
        now = self.clock()
        if self._last_wall_time is None:
            self._last_wall_time = now
            return self.session.state()
        elapsed = max(0.0, now - self._last_wall_time)
        self._last_wall_time = now
        timestep = float(self.session.model.opt.timestep)
        maximum_budget = timestep * self.max_catch_up_steps
        self._time_accumulator = min(
            self._time_accumulator + elapsed,
            maximum_budget,
        )
        steps = min(
            int(math.floor((self._time_accumulator + timestep * 1e-9) / timestep)),
            self.max_catch_up_steps,
        )
        if steps < 1:
            return self.session.state()
        self._time_accumulator = max(
            0.0, self._time_accumulator - steps * timestep
        )
        return self.session.step(steps)

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
        self._last_wall_time = None
        self._time_accumulator = 0.0
        self.console("Simulation reset.")

    def _create_session(self, scene: Scene) -> MuJoCoSimulationSession:
        export_path = self.project_root / "exports" / "scene.xml"
        return MuJoCoSimulationSession(scene, export_path, asset_root=self.project_root)

    def _read_max_catch_up_steps(self, scene: Scene) -> int:
        raw_value = scene.simulation_config.get(
            "max_catch_up_steps", self.default_max_catch_up_steps
        )
        if isinstance(raw_value, bool):
            raise ValueError("simulation_config.max_catch_up_steps must be an integer >= 1")
        value = int(raw_value)
        if value < 1 or float(raw_value) != value:
            raise ValueError("simulation_config.max_catch_up_steps must be an integer >= 1")
        return value
