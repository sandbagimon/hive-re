from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from simlab.models.scene import Scene
from simlab.services.mjcf_exporter import export_scene_to_mjcf
from simlab.services.openusd_importer import import_openusd_asset, load_visual_geometry
from simlab.services.physics_materials import material_for_id
from simlab.services.physics_validation import PhysicsPreflightReport, run_physics_preflight
from simlab.services.project_service import load_scene, save_scene, validate_scene
from simlab.services.simulation_service import SimulationService


class EditorBridge(QObject):
    """JSON RPC boundary between the TypeScript editor and Python services."""

    simulationStateChanged = Signal(str)
    simulationStatusChanged = Signal(str)
    consoleMessage = Signal(str)
    titleChanged = Signal(str)

    def __init__(self, parent_widget: QWidget, project_root: Path) -> None:
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.project_root = project_root
        self.current_path: Path | None = None
        self.synced_scene_json = json.dumps(Scene().to_dict())
        self.dirty = False
        self.simulation_service = SimulationService(project_root, self.consoleMessage.emit)
        self.simulation_timer = QTimer(self)
        self.simulation_timer.setInterval(16)
        self.simulation_timer.timeout.connect(self._advance_simulation)

    @Slot(result=str)
    def getAssets(self) -> str:
        try:
            metadata_path = self.project_root / "assets" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            assets = [self._enrich_asset(asset) for asset in metadata.get("assets", [])]
            return self._success({"assets": assets})
        except Exception as exc:
            return self._failure(exc)

    @Slot(result=str)
    def importOpenUsd(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self.parent_widget,
            "Import OpenUSD Asset",
            str(self.project_root),
            "OpenUSD (*.usd *.usda *.usdc *.usdz)",
        )
        if not path:
            return self._failure("Cancelled")
        try:
            result = import_openusd_asset(path, self.project_root)
            asset = self._enrich_asset(result.asset)
            self.consoleMessage.emit(f"Imported OpenUSD asset: {asset['name']}")
            for warning in result.warnings:
                self.consoleMessage.emit(f"OpenUSD import warning: {warning}")
            return self._success(
                {
                    "asset": asset,
                    "warnings": result.warnings,
                    "robotics": (
                        result.robotics_model.to_dict()
                        if result.robotics_model is not None
                        else None
                    ),
                }
            )
        except Exception as exc:
            return self._failure(exc)

    @Slot(str, result=str)
    def getVisualGeometry(self, cache_path: str) -> str:
        try:
            return self._success(load_visual_geometry(cache_path, self.project_root))
        except Exception as exc:
            return self._failure(exc)

    @Slot(result=str)
    def openProject(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self.parent_widget,
            "Open Scene",
            str(self.project_root),
            "JSON (*.json)",
        )
        if not path:
            return self._failure("Cancelled")
        try:
            scene = load_scene(path)
            self._reset_simulation()
            self.current_path = Path(path)
            self.synced_scene_json = json.dumps(scene.to_dict())
            self.dirty = False
            self._emit_title(scene.name)
            return self._success({"scene": scene.to_dict(), "path": path})
        except Exception as exc:
            return self._failure(exc)

    @Slot(str, bool, result=str)
    def saveProject(self, scene_json: str, save_as: bool) -> str:
        try:
            scene = self._scene_from_json(scene_json)
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
            save_scene(path, scene)
            self.current_path = path
            self.synced_scene_json = scene_json
            self.dirty = False
            self._emit_title(scene.name)
            return self._success({"path": str(path)})
        except Exception as exc:
            return self._failure(exc)

    @Slot(str, result=str)
    def preflight(self, scene_json: str) -> str:
        try:
            report = run_physics_preflight(
                self._scene_from_json(scene_json), asset_root=self.project_root
            )
            return self._success(self._preflight_payload(report))
        except Exception as exc:
            return self._failure(exc)

    @Slot(str, result=str)
    def exportMjcf(self, scene_json: str) -> str:
        try:
            scene = self._scene_from_json(scene_json)
            report = run_physics_preflight(scene, asset_root=self.project_root)
            payload = self._preflight_payload(report)
            if not report.is_valid:
                return self._failure("Physics preflight failed", payload)
            path = export_scene_to_mjcf(
                scene,
                self.project_root / "exports" / "scene.xml",
                asset_root=self.project_root,
            )
            return self._success({"path": str(path), "issues": payload["issues"]})
        except Exception as exc:
            return self._failure(exc)

    @Slot(str, result=str)
    def runSimulation(self, scene_json: str) -> str:
        try:
            scene = self._scene_from_json(scene_json)
            report = run_physics_preflight(scene, asset_root=self.project_root)
            payload = self._preflight_payload(report)
            if not report.is_valid:
                return self._failure("Physics preflight failed", payload)
            state = self.simulation_service.start(scene)
            self.simulation_timer.start()
            self.simulationStatusChanged.emit("running")
            return self._success({"state": state.to_dict(), "issues": payload["issues"]})
        except Exception as exc:
            return self._failure(exc)

    @Slot(result=str)
    def pauseSimulation(self) -> str:
        if self.simulation_service.session is None:
            return self._failure("No simulation is loaded")
        self.simulation_timer.stop()
        self.simulation_service.pause()
        self.simulationStatusChanged.emit("paused")
        return self._success()

    @Slot(str, result=str)
    def stepSimulation(self, scene_json: str) -> str:
        self.simulation_timer.stop()
        try:
            scene = self._scene_from_json(scene_json)
            report = run_physics_preflight(scene, asset_root=self.project_root)
            payload = self._preflight_payload(report)
            if not report.is_valid:
                return self._failure("Physics preflight failed", payload)
            state = self.simulation_service.step_once(scene)
            self.simulationStatusChanged.emit("paused")
            return self._success({"state": state.to_dict(), "issues": payload["issues"]})
        except Exception as exc:
            return self._failure(exc)

    @Slot(result=str)
    def resetSimulation(self) -> str:
        self._reset_simulation()
        return self._success()

    @Slot(str, str, result=str)
    def setJointTargets(self, scene_json: str, targets_json: str) -> str:
        try:
            scene = self._scene_from_json(scene_json)
            targets = json.loads(targets_json)
            if not isinstance(targets, dict):
                raise ValueError("Joint targets must be a JSON object")
            numeric_targets = {str(key): float(value) for key, value in targets.items()}
            state = self.simulation_service.set_joint_position_targets(
                scene, numeric_targets
            )
            self.simulationStateChanged.emit(json.dumps(state.to_dict()))
            return self._success({"state": state.to_dict()})
        except Exception as exc:
            session = self.simulation_service.session
            data = {"state": session.state().to_dict()} if session is not None else None
            return self._failure(exc, data)

    @Slot(str, bool, str)
    def setEditorState(self, scene_json: str, dirty: bool, current_path: str) -> None:
        scene_changed = scene_json != self.synced_scene_json
        if scene_changed and self.simulation_service.session is not None:
            self._reset_simulation()
        self.synced_scene_json = scene_json
        self.dirty = dirty
        self.current_path = Path(current_path) if current_path else None
        try:
            scene_name = str(json.loads(scene_json).get("name", "Untitled Scene"))
        except (json.JSONDecodeError, AttributeError):
            scene_name = "Untitled Scene"
        self._emit_title(scene_name)

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
        response = json.loads(self.saveProject(self.synced_scene_json, False))
        return bool(response.get("ok"))

    def shutdown(self) -> None:
        self._reset_simulation()

    def _advance_simulation(self) -> None:
        try:
            state = self.simulation_service.step_frame()
        except Exception as exc:
            self.simulation_timer.stop()
            self.consoleMessage.emit(f"Simulation fault: {exc}")
            self.simulationStatusChanged.emit("fault")
            return
        if state is None:
            self.simulation_timer.stop()
            return
        self.simulationStateChanged.emit(json.dumps(state.to_dict()))

    def _reset_simulation(self) -> None:
        self.simulation_timer.stop()
        if self.simulation_service.session is not None:
            self.simulation_service.reset()
        self.simulationStatusChanged.emit("stopped")

    def _scene_from_json(self, scene_json: str) -> Scene:
        data = json.loads(scene_json)
        if not isinstance(data, dict):
            raise ValueError("Scene payload must be a JSON object")
        scene = Scene.from_dict(data)
        validate_scene(scene)
        return scene

    def _enrich_asset(self, source: dict[str, Any]) -> dict[str, Any]:
        asset = copy.deepcopy(source)
        properties = asset.get("default_properties")
        if not isinstance(properties, dict):
            return asset
        physics = properties.get("physics")
        if not isinstance(physics, dict) or "material" not in physics:
            return asset
        values = material_for_id(physics["material"]).property_values()
        values.update(physics)
        properties["physics"] = values
        return asset

    def _preflight_payload(self, report: PhysicsPreflightReport) -> dict[str, Any]:
        return {
            "valid": report.is_valid,
            "issues": [asdict(issue) for issue in report.issues],
        }

    def _emit_title(self, scene_name: str) -> None:
        dirty = "*" if self.dirty else ""
        path = f" - {self.current_path}" if self.current_path else ""
        self.titleChanged.emit(f"{dirty}SimLab - {scene_name}{path}")

    @staticmethod
    def _success(data: Any = None) -> str:
        payload: dict[str, Any] = {"ok": True}
        if data is not None:
            payload["data"] = data
        return json.dumps(payload)

    @staticmethod
    def _failure(error: object, data: Any = None) -> str:
        payload: dict[str, Any] = {"ok": False, "error": str(error)}
        if data is not None:
            payload["data"] = data
        return json.dumps(payload)
