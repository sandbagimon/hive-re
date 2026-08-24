from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from beefoundrysim.web_application import WebApplication


class EditorBridge(QObject):
    """Optional Qt WebChannel adapter over the transport-neutral application API."""

    simulationStateChanged = Signal(str)
    simulationStatusChanged = Signal(str)
    consoleMessage = Signal(str)
    titleChanged = Signal(str)

    def __init__(self, parent_widget: QWidget, project_root: Path) -> None:
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.project_root = project_root
        self.application = WebApplication(
            project_root,
            background_simulation=False,
            restrict_paths=False,
        )
        self.simulation_service = self.application.simulation_service
        self._event_sequence = 0
        self.simulation_timer = QTimer(self)
        self.simulation_timer.setInterval(16)
        self.simulation_timer.timeout.connect(self._advance_simulation)

    @property
    def current_path(self) -> Path | None:
        return self.application.current_path

    @property
    def synced_scene_json(self) -> str:
        return self.application.synced_scene_json

    @property
    def dirty(self) -> bool:
        return self.application.dirty

    @dirty.setter
    def dirty(self, value: bool) -> None:
        self.application.dirty = value

    @Slot(result=str)
    def getAssets(self) -> str:
        return self._call("getAssets")

    @Slot(result=str)
    def importOpenUsd(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self.parent_widget,
            "Import OpenUSD Asset",
            str(self.project_root),
            "OpenUSD (*.usd *.usda *.usdc *.usdz)",
        )
        return self.importOpenUsdPath(path) if path else self._failure("Cancelled")

    @Slot(str, result=str)
    def importOpenUsdPath(self, path: str) -> str:
        return self._call("importOpenUsdPath", path)

    @Slot(str, result=str)
    def getVisualGeometry(self, cache_path: str) -> str:
        return self._call("getVisualGeometry", cache_path)

    @Slot(result=str)
    def openProject(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self.parent_widget, "Open Scene", str(self.project_root), "JSON (*.json)"
        )
        return self.openProjectPath(path) if path else self._failure("Cancelled")

    @Slot(str, result=str)
    def openProjectPath(self, path: str) -> str:
        self.simulation_timer.stop()
        return self._call("openProjectPath", path)

    @Slot(str, bool, result=str)
    def saveProject(self, scene_json: str, save_as: bool) -> str:
        path = self.current_path
        if save_as or path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self.parent_widget,
                "Save Scene",
                str(path or self.project_root / "scene.json"),
                "JSON (*.json)",
            )
            if not selected:
                return self._failure("Cancelled")
            path = Path(selected)
        return self.saveProjectPath(scene_json, str(path))

    @Slot(str, str, result=str)
    def saveProjectPath(self, scene_json: str, path: str) -> str:
        return self._call("saveProjectPath", scene_json, path)

    @Slot(str, result=str)
    def preflight(self, scene_json: str) -> str:
        return self._call("preflight", scene_json)

    @Slot(str, result=str)
    def exportMjcf(self, scene_json: str) -> str:
        return self._call("exportMjcf", scene_json)

    @Slot(str, result=str)
    def runSimulation(self, scene_json: str) -> str:
        result = self._call("runSimulation", scene_json)
        if self._ok(result):
            self.simulation_timer.start()
        return result

    @Slot(result=str)
    def pauseSimulation(self) -> str:
        self.simulation_timer.stop()
        return self._call("pauseSimulation")

    @Slot(float, result=str)
    def setSimulationSpeed(self, factor: float) -> str:
        return self._call("setSimulationSpeed", factor)

    @Slot(str, result=str)
    def stepSimulation(self, scene_json: str) -> str:
        self.simulation_timer.stop()
        return self._call("stepSimulation", scene_json)

    @Slot(result=str)
    def resetSimulation(self) -> str:
        self.simulation_timer.stop()
        return self._call("resetSimulation")

    @Slot(str, str, result=str)
    def setJointTargets(self, scene_json: str, targets_json: str) -> str:
        return self._call("setJointTargets", scene_json, targets_json)

    @Slot(str, str, result=str)
    def setActuatorControls(self, scene_json: str, controls_json: str) -> str:
        return self._call("setActuatorControls", scene_json, controls_json)

    @Slot(str, result=str)
    def loadController(self, scene_json: str) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self.parent_widget,
            "Load Python Controller",
            str(self.project_root / "controllers"),
            "Python (*.py)",
        )
        return (
            self.loadControllerPath(scene_json, path)
            if path
            else self._failure("Cancelled")
        )

    @Slot(str, str, result=str)
    def loadControllerPath(self, scene_json: str, path: str) -> str:
        self.simulation_timer.stop()
        return self._call("loadControllerPath", scene_json, path)

    @Slot(result=str)
    def detachController(self) -> str:
        self.simulation_timer.stop()
        return self._call("detachController")

    @Slot(str, str, result=str)
    def loadTrajectory(self, scene_json: str, trajectory_json: str) -> str:
        self.simulation_timer.stop()
        return self._call("loadTrajectory", scene_json, trajectory_json)

    @Slot(result=str)
    def playTrajectory(self) -> str:
        result = self._call("playTrajectory")
        if self._ok(result):
            self.simulation_timer.start()
        return result

    @Slot(result=str)
    def pauseTrajectory(self) -> str:
        self.simulation_timer.stop()
        return self._call("pauseTrajectory")

    @Slot(result=str)
    def stopTrajectory(self) -> str:
        self.simulation_timer.stop()
        return self._call("stopTrajectory")

    @Slot(str, str, result=str)
    def startRecording(self, scene_json: str, config_json: str) -> str:
        return self._call("startRecording", scene_json, config_json)

    @Slot(result=str)
    def stopRecording(self) -> str:
        return self._call("stopRecording")

    @Slot(result=str)
    def getRecording(self) -> str:
        return self._call("getRecording")

    @Slot(str, str, result=str)
    def exportRecording(self, path: str, format_name: str) -> str:
        return self._call("exportRecording", path, format_name)

    @Slot(str, result=str)
    def exportRecordingDialog(self, format_name: str) -> str:
        if format_name not in {"json", "csv"}:
            return self._failure("Recording format must be 'json' or 'csv'")
        selected, _ = QFileDialog.getSaveFileName(
            self.parent_widget,
            "Export Joint Recording",
            str(self.project_root / "recordings" / f"joint-recording.{format_name}"),
            f"{format_name.upper()} (*.{format_name})",
        )
        return (
            self.exportRecording(selected, format_name)
            if selected
            else self._failure("Cancelled")
        )

    @Slot(str, bool, str)
    def setEditorState(self, scene_json: str, dirty: bool, current_path: str) -> None:
        self._call("setEditorState", scene_json, dirty, current_path)
        if not self.application.is_advancing:
            self.simulation_timer.stop()

    def confirm_close(self) -> bool:
        if not self.dirty:
            return True
        result = QMessageBox.warning(
            self.parent_widget,
            "Unsaved Changes",
            "The current scene has unsaved changes.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if result == QMessageBox.StandardButton.Cancel:
            return False
        if result == QMessageBox.StandardButton.Discard:
            return True
        return self._ok(self.saveProject(self.synced_scene_json, False))

    def shutdown(self) -> None:
        self.simulation_timer.stop()
        self.application.close()
        self._flush_events()

    def _advance_simulation(self) -> None:
        self.application.advance_frame(force=True)
        self._flush_events()
        if not self.application.is_advancing:
            self.simulation_timer.stop()

    def _stop_simulation(self) -> None:
        self.simulation_timer.stop()
        self.application.stop_simulation()
        self._flush_events()

    def _call(self, method: str, *args: Any) -> str:
        result = self.application.dispatch(method, list(args))
        self._flush_events()
        return json.dumps(result)

    def _flush_events(self) -> None:
        for event in self.application.events_since(self._event_sequence):
            self._event_sequence = int(event["sequence"])
            event_type = event["type"]
            payload = event["payload"]
            if event_type == "state":
                self.simulationStateChanged.emit(json.dumps(payload))
            elif event_type == "status":
                self.simulationStatusChanged.emit(str(payload))
            elif event_type == "console":
                self.consoleMessage.emit(str(payload))
            elif event_type == "title":
                self.titleChanged.emit(str(payload))

    @staticmethod
    def _ok(response_json: str) -> bool:
        try:
            return bool(json.loads(response_json).get("ok"))
        except (json.JSONDecodeError, AttributeError):
            return False

    @staticmethod
    def _failure(error: object, data: Any = None) -> str:
        payload: dict[str, Any] = {"ok": False, "error": str(error)}
        if data is not None:
            payload["data"] = data
        return json.dumps(payload)
