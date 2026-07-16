from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from pathlib import Path

from simlab.models.recording import JointStateRecording
from simlab.models.scene import Scene
from simlab.models.trajectory import JointTrajectory
from simlab.services.controller_runtime import StepController
from simlab.services.simulation_session import (
    ClockSimulationState,
    MuJoCoSimulationSession,
    SimulationState,
)

ConsoleCallback = Callable[[str], None]
Clock = Callable[[], float]


class SimulationService:
    """Manage an in-process MuJoCo session for live viewport state sync."""

    SUPPORTED_REALTIME_FACTORS = (0.25, 0.5, 1.0, 2.0)

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
        self.target_realtime_factor = 1.0
        self._last_wall_time: float | None = None
        self._time_accumulator = 0.0
        self._rtf_wall_elapsed = 0.0
        self._rtf_simulated_elapsed = 0.0

    def is_running(self) -> bool:
        return self.running

    def start(self, scene: Scene) -> SimulationState:
        self.max_catch_up_steps = self._read_max_catch_up_steps(scene)
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        self.running = True
        self._reset_clock_tracking(running=True)
        self.console("Simulation running.")
        return self._with_clock(self.session.state())

    def pause(self) -> None:
        if not self.session:
            self.console("No simulation is loaded.")
            return
        self.running = False
        self._reset_clock_tracking()
        self.console("Simulation paused.")

    def step_once(self, scene: Scene) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        self.running = False
        self._reset_clock_tracking()
        state = self.session.step()
        self.console(f"Simulation step: t={state.time:.3f}")
        return self._with_clock(state)

    def step_frame(self) -> SimulationState | None:
        if not self.running or self.session is None:
            return None
        try:
            now = self.clock()
            if self._last_wall_time is None:
                self._last_wall_time = now
                return self.session.state()
            elapsed = max(0.0, now - self._last_wall_time)
            self._last_wall_time = now
            self._rtf_wall_elapsed += elapsed
            timestep = float(self.session.model.opt.timestep)
            maximum_budget = timestep * self.max_catch_up_steps
            self._time_accumulator = min(
                self._time_accumulator + elapsed * self.target_realtime_factor,
                maximum_budget,
            )
            steps = min(
                int(
                    math.floor(
                        (self._time_accumulator + timestep * 1e-9) / timestep
                    )
                ),
                self.max_catch_up_steps,
            )
            if steps < 1:
                return self._with_clock(self.session.state())
            self._time_accumulator = max(
                0.0, self._time_accumulator - steps * timestep
            )
            state = self.session.step(steps)
            self._rtf_simulated_elapsed += steps * timestep
            if state.trajectory.status == "completed":
                self.running = False
                self._last_wall_time = None
                self._time_accumulator = 0.0
            return self._with_clock(state)
        except Exception:
            self.running = False
            self._reset_clock_tracking()
            raise

    def set_realtime_factor(self, value: float) -> SimulationState | None:
        factor = float(value)
        if not math.isfinite(factor) or factor not in self.SUPPORTED_REALTIME_FACTORS:
            supported = ", ".join(f"{item:g}x" for item in self.SUPPORTED_REALTIME_FACTORS)
            raise ValueError(f"Real-time factor must be one of: {supported}")
        self.target_realtime_factor = factor
        self._reset_clock_tracking(running=self.running, preserve_accumulator=True)
        self.console(f"Simulation speed set to {factor:g}x.")
        if self.session is None:
            return None
        return self._with_clock(self.session.state())

    def set_joint_position_targets(
        self, scene: Scene, targets: dict[str, float]
    ) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        state = self.session.set_joint_position_targets(targets)
        self.console(f"Updated {len(targets)} joint target(s).")
        return self._with_clock(state)

    def attach_controller(
        self,
        scene: Scene,
        controller: StepController,
        *,
        name: str | None = None,
    ) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        state = self.session.attach_controller(controller, name=name)
        self.console(f"Attached Python controller: {name or type(controller).__name__}")
        return self._with_clock(state)

    def detach_controller(self) -> SimulationState:
        if self.session is None:
            raise RuntimeError("No simulation is loaded")
        state = self.session.detach_controller()
        self.console("Detached Python controller.")
        return self._with_clock(state)

    def load_joint_trajectory(
        self,
        scene: Scene,
        trajectory: JointTrajectory,
    ) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        self.running = False
        self._reset_clock_tracking()
        state = self.session.load_joint_trajectory(trajectory)
        self.console(f"Loaded joint trajectory: {trajectory.name}")
        return self._with_clock(state)

    def play_trajectory(self) -> SimulationState:
        if self.session is None:
            raise RuntimeError("No simulation is loaded")
        state = self.session.play_trajectory()
        self.running = True
        self._reset_clock_tracking(running=True)
        self.console("Trajectory playing.")
        return self._with_clock(state)

    def pause_trajectory(self) -> SimulationState:
        if self.session is None:
            raise RuntimeError("No simulation is loaded")
        state = self.session.pause_trajectory()
        self.running = False
        self._reset_clock_tracking()
        self.console("Trajectory paused.")
        return self._with_clock(state)

    def stop_trajectory(self) -> SimulationState:
        if self.session is None:
            raise RuntimeError("No simulation is loaded")
        state = self.session.stop_trajectory()
        self.running = False
        self._reset_clock_tracking()
        self.console("Trajectory stopped.")
        return self._with_clock(state)

    def start_joint_recording(
        self,
        scene: Scene,
        *,
        name: str,
        joint_ids: list[str] | None = None,
        actuator_ids: list[str] | None = None,
    ) -> SimulationState:
        if self.session is None:
            self.session = self._create_session(scene)
            self.console(f"Loaded MuJoCo model: {self.session.xml_path}")
        state = self.session.start_joint_recording(
            name=name,
            joint_ids=joint_ids,
            actuator_ids=actuator_ids,
        )
        self.console(f"Joint state recording started: {name}")
        return self._with_clock(state)

    def stop_joint_recording(self) -> tuple[SimulationState, JointStateRecording]:
        if self.session is None:
            raise RuntimeError("No simulation is loaded")
        state, recording = self.session.stop_joint_recording()
        self.console(
            f"Joint state recording stopped: {len(recording.samples)} sample(s)."
        )
        return self._with_clock(state), recording

    def get_joint_recording(self) -> JointStateRecording:
        recording = self.session.joint_recording if self.session is not None else None
        if recording is None:
            raise RuntimeError("No joint state recording is available")
        return recording

    def export_joint_recording(self, path: str | Path, format_name: str) -> Path:
        recording = self.get_joint_recording()
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if format_name == "json":
            content = json.dumps(recording.to_dict(), indent=2) + "\n"
        elif format_name == "csv":
            content = recording.to_csv()
        else:
            raise ValueError("Recording format must be 'json' or 'csv'")
        output_path.write_text(content, encoding="utf-8")
        self.console(f"Exported joint state recording: {output_path}")
        return output_path

    def reset(self) -> SimulationState | None:
        if self.session is None:
            self.console("No simulation is loaded.")
            return None
        state = self.session.reset()
        self.running = False
        self._reset_clock_tracking()
        self.console("Simulation reset.")
        return self._with_clock(state)

    def stop(self) -> None:
        self.session = None
        self.running = False
        self._reset_clock_tracking()
        self.console("Simulation stopped.")

    def _with_clock(self, state: SimulationState) -> SimulationState:
        timestep = float(self.session.model.opt.timestep) if self.session else 0.0
        actual = (
            self._rtf_simulated_elapsed / self._rtf_wall_elapsed
            if self._rtf_wall_elapsed > 0.0
            else 0.0
        )
        state.clock = ClockSimulationState(
            target_rtf=self.target_realtime_factor,
            actual_rtf=actual,
            timestep=timestep,
        )
        return state

    def _reset_clock_tracking(
        self,
        *,
        running: bool = False,
        preserve_accumulator: bool = False,
    ) -> None:
        self._last_wall_time = self.clock() if running else None
        if not preserve_accumulator:
            self._time_accumulator = 0.0
        self._rtf_wall_elapsed = 0.0
        self._rtf_simulated_elapsed = 0.0

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
