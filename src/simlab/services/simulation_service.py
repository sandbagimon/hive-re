from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from simlab.models.scene import Scene
from simlab.services.mjcf_exporter import export_scene_to_mjcf

ConsoleCallback = Callable[[str], None]


class SimulationService:
    """Export scenes and run the headless MuJoCo runner as a subprocess."""

    def __init__(self, project_root: Path, console: ConsoleCallback | None = None) -> None:
        self.project_root = project_root
        self.console = console or print
        self.process: subprocess.Popen[str] | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def run(self, scene: Scene) -> None:
        if self.is_running():
            self.console("Simulation is already running.")
            return

        export_path = self.project_root / "exports" / "scene.xml"
        export_scene_to_mjcf(scene, export_path)
        self.console(f"Exported MJCF: {export_path}")

        env = os.environ.copy()
        src_path = str(self.project_root / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        command = [sys.executable, "-m", "simlab.simulation.mujoco_runner", str(export_path)]

        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.project_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self.console(f"Could not start simulation runner: {exc}")
            self.process = None
            return

        threading.Thread(target=self._stream_output, daemon=True).start()

    def stop(self) -> None:
        if not self.is_running():
            self.console("No simulation is running.")
            return
        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.console("Simulation stopped.")
        self.process = None

    def _stream_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.console(line.rstrip())
        return_code = process.wait()
        self.console(f"Simulation exited with code {return_code}.")
        if self.process is process:
            self.process = None
