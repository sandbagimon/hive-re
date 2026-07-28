from __future__ import annotations

import base64
import copy
import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from simlab.models.scene import Scene
from simlab.models.trajectory import JointTrajectory
from simlab.services.mjcf_exporter import export_scene_to_mjcf
from simlab.services.openusd_importer import import_openusd_asset, load_visual_geometry
from simlab.services.physics_materials import material_for_id
from simlab.services.physics_validation import PhysicsPreflightReport, run_physics_preflight
from simlab.services.project_service import load_scene, save_scene, validate_scene
from simlab.services.simulation_service import SimulationService


class WebApplication:
    """Transport-neutral SimLab application boundary used by the web server."""

    def __init__(
        self,
        project_root: Path,
        *,
        background_simulation: bool = True,
        restrict_paths: bool = True,
    ) -> None:
        self.project_root = project_root.resolve()
        self.current_path: Path | None = None
        self.synced_scene_json = json.dumps(Scene().to_dict())
        self.dirty = False
        self._lock = threading.RLock()
        self._running = False
        self._closed = threading.Event()
        self._event_sequence = 0
        self._events: list[dict[str, Any]] = []
        self._restrict_paths = restrict_paths
        self.simulation_service = SimulationService(project_root, self._console)
        self._thread: threading.Thread | None = None
        if background_simulation:
            self._thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self._thread.start()

    def dispatch(self, method: str, args: list[Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[..., Any]] = {
            "getAssets": self.get_assets,
            "importOpenUsd": self.path_required,
            "importOpenUsdPath": self.import_openusd_path,
            "importOpenUsdBundle": self.import_openusd_bundle,
            "getVisualGeometry": self.get_visual_geometry,
            "openProject": self.path_required,
            "openProjectPath": self.open_project_path,
            "openProjectContent": self.open_project_content,
            "saveProject": self.save_project,
            "saveProjectPath": self.save_project_path,
            "validateProjectContent": self.validate_project_content,
            "preflight": self.preflight,
            "exportMjcf": self.export_mjcf,
            "runSimulation": self.run_simulation,
            "pauseSimulation": self.pause_simulation,
            "setSimulationSpeed": self.set_simulation_speed,
            "stepSimulation": self.step_simulation,
            "resetSimulation": self.reset_simulation,
            "setJointTargets": self.set_joint_targets,
            "loadController": self.path_required,
            "loadControllerPath": self.load_controller_path,
            "loadControllerContent": self.load_controller_content,
            "detachController": self.detach_controller,
            "loadTrajectory": self.load_trajectory,
            "playTrajectory": self.play_trajectory,
            "pauseTrajectory": self.pause_trajectory,
            "stopTrajectory": self.stop_trajectory,
            "startRecording": self.start_recording,
            "stopRecording": self.stop_recording,
            "getRecording": self.get_recording,
            "exportRecording": self.export_recording,
            "exportRecordingDialog": self.path_required,
            "getRecordingExport": self.get_recording_export,
            "setEditorState": self.set_editor_state,
        }
        handler = handlers.get(method)
        if handler is None:
            return self.failure(f"Unknown RPC method: {method}")
        try:
            with self._lock:
                result = handler(*args)
            return result if isinstance(result, dict) else self.success(result)
        except Exception as exc:
            return self.failure(exc)

    def get_assets(self) -> dict[str, Any]:
        metadata_path = self.project_root / "assets" / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assets = [self._enrich_asset(asset) for asset in metadata.get("assets", [])]
        return self.success({"assets": assets})

    def path_required(self, *_args: Any) -> dict[str, Any]:
        return self.failure("This browser operation requires an explicit local path")

    def import_openusd_path(self, path: str) -> dict[str, Any]:
        result = import_openusd_asset(self._project_path(path), self.project_root)
        asset = self._enrich_asset(result.asset)
        self._console(f"Imported OpenUSD asset: {asset['name']}")
        for warning in result.warnings:
            self._console(f"OpenUSD import warning: {warning}")
        robotics = result.robotics_model.to_dict() if result.robotics_model else None
        return self.success({"asset": asset, "warnings": result.warnings, "robotics": robotics})

    def import_openusd_bundle(self, bundle_json: str, entry_name: str) -> dict[str, Any]:
        bundle = json.loads(bundle_json)
        if not isinstance(bundle, list) or not bundle:
            raise ValueError("OpenUSD upload bundle must contain at least one file")
        upload_root = self.project_root / "assets" / "uploads" / uuid.uuid4().hex
        total_bytes = 0
        entry_path: Path | None = None
        for item in bundle:
            if not isinstance(item, dict):
                raise ValueError("OpenUSD upload entry must be an object")
            relative = self._safe_relative_path(str(item.get("name", "")))
            encoded = item.get("content")
            if not isinstance(encoded, str):
                raise ValueError(f"OpenUSD upload content is missing: {relative}")
            content = base64.b64decode(encoded, validate=True)
            total_bytes += len(content)
            if total_bytes > 256 * 1024 * 1024:
                raise ValueError("OpenUSD upload bundle exceeds 256 MiB")
            output = upload_root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
            if relative.as_posix() == entry_name:
                entry_path = output
        if entry_path is None:
            raise ValueError(f"OpenUSD entry file is not present in upload: {entry_name}")
        return self.import_openusd_path(str(entry_path))

    def get_visual_geometry(self, cache_path: str) -> dict[str, Any]:
        return self.success(load_visual_geometry(cache_path, self.project_root))

    def open_project_path(self, path: str) -> dict[str, Any]:
        source_path = self._project_path(path)
        scene = load_scene(source_path)
        self._stop_simulation()
        self.current_path = source_path
        self.synced_scene_json = json.dumps(scene.to_dict())
        self.dirty = False
        self._publish("title", self._title(scene.name))
        return self.success({"scene": scene.to_dict(), "path": str(source_path)})

    def open_project_content(self, scene_json: str, display_name: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        self._stop_simulation()
        self.current_path = None
        self.synced_scene_json = json.dumps(scene.to_dict())
        self.dirty = False
        self._publish("title", self._title(scene.name))
        return self.success({"scene": scene.to_dict(), "path": display_name})

    def save_project(self, scene_json: str, save_as: bool) -> dict[str, Any]:
        if save_as or self.current_path is None:
            return self.failure("This browser operation requires an explicit local path")
        return self.save_project_path(scene_json, str(self.current_path))

    def save_project_path(self, scene_json: str, path: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        output_path = self._project_path(path)
        save_scene(output_path, scene)
        self.current_path = output_path
        self.synced_scene_json = scene_json
        self.dirty = False
        self._publish("title", self._title(scene.name))
        return self.success({"path": str(output_path)})

    def validate_project_content(self, scene_json: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        return self.success({"scene": scene.to_dict()})

    def preflight(self, scene_json: str) -> dict[str, Any]:
        report = run_physics_preflight(
            self._scene_from_json(scene_json), asset_root=self.project_root
        )
        return self.success(self._preflight_payload(report))

    def export_mjcf(self, scene_json: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        report = run_physics_preflight(scene, asset_root=self.project_root)
        payload = self._preflight_payload(report)
        if not report.is_valid:
            return self.failure("Physics preflight failed", payload)
        path = export_scene_to_mjcf(
            scene, self.project_root / "exports" / "scene.xml", asset_root=self.project_root
        )
        return self.success(
            {
                "path": str(path),
                "filename": path.name,
                "content": path.read_text(encoding="utf-8"),
                "issues": payload["issues"],
            }
        )

    def run_simulation(self, scene_json: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        report = run_physics_preflight(scene, asset_root=self.project_root)
        payload = self._preflight_payload(report)
        if not report.is_valid:
            return self.failure("Physics preflight failed", payload)
        state = self.simulation_service.start(scene)
        self._running = True
        self._publish("status", "running")
        return self.success({"state": state.to_dict(), "issues": payload["issues"]})

    def pause_simulation(self) -> dict[str, Any]:
        if self.simulation_service.session is None:
            return self.failure("No simulation is loaded")
        self._running = False
        self.simulation_service.pause()
        self._publish("status", "paused")
        return self.success()

    def set_simulation_speed(self, factor: float) -> dict[str, Any]:
        state = self.simulation_service.set_realtime_factor(float(factor))
        if state is not None:
            self._publish("state", state.to_dict())
        return self.success({
            "target_rtf": self.simulation_service.target_realtime_factor,
            "state": state.to_dict() if state else None,
        })

    def step_simulation(self, scene_json: str) -> dict[str, Any]:
        self._running = False
        scene = self._scene_from_json(scene_json)
        report = run_physics_preflight(scene, asset_root=self.project_root)
        payload = self._preflight_payload(report)
        if not report.is_valid:
            return self.failure("Physics preflight failed", payload)
        state = self.simulation_service.step_once(scene)
        self._publish("status", "paused")
        self._publish("state", state.to_dict())
        return self.success({"state": state.to_dict(), "issues": payload["issues"]})

    def reset_simulation(self) -> dict[str, Any]:
        self._running = False
        state = self.simulation_service.reset()
        if state is None:
            self._publish("status", "stopped")
            return self.success({"state": None})
        payload = state.to_dict()
        self._publish("state", payload)
        self._publish("status", "paused")
        return self.success({"state": payload})

    def set_joint_targets(self, scene_json: str, targets_json: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        targets = json.loads(targets_json)
        if not isinstance(targets, dict):
            raise ValueError("Joint targets must be a JSON object")
        numeric = {str(key): float(value) for key, value in targets.items()}
        try:
            state = self.simulation_service.set_joint_position_targets(scene, numeric)
        except Exception as exc:
            session = self.simulation_service.session
            data = {"state": session.state().to_dict()} if session else None
            return self.failure(exc, data)
        self._publish("state", state.to_dict())
        return self.success({"state": state.to_dict()})

    def load_controller_path(self, scene_json: str, path: str) -> dict[str, Any]:
        self._running = False
        state, loaded = self.simulation_service.load_project_controller(
            self._scene_from_json(scene_json), self._project_path(path)
        )
        payload = state.to_dict()
        self._publish("state", payload)
        self._publish("status", "paused")
        return self.success({"state": payload, "controller": loaded.metadata()})

    def load_controller_content(
        self, scene_json: str, filename: str, source: str
    ) -> dict[str, Any]:
        relative = self._safe_relative_path(filename)
        if relative.suffix.lower() != ".py":
            raise ValueError("Controller upload must be a .py file")
        path = self.project_root / "controllers" / "uploads" / uuid.uuid4().hex / relative.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return self.load_controller_path(scene_json, str(path))

    def detach_controller(self) -> dict[str, Any]:
        self._running = False
        if self.simulation_service.is_running():
            self.simulation_service.pause()
        state = self.simulation_service.detach_controller()
        payload = state.to_dict()
        self._publish("state", payload)
        self._publish("status", "paused")
        return self.success({"state": payload})

    def load_trajectory(self, scene_json: str, trajectory_json: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        report = run_physics_preflight(scene, asset_root=self.project_root)
        payload = self._preflight_payload(report)
        if not report.is_valid:
            return self.failure("Physics preflight failed", payload)
        data = json.loads(trajectory_json)
        if not isinstance(data, dict):
            raise ValueError("Trajectory payload must be a JSON object")
        self._running = False
        state = self.simulation_service.load_joint_trajectory(
            scene, JointTrajectory.from_dict(data)
        )
        self._publish("state", state.to_dict())
        self._publish("status", "paused")
        return self.success({"state": state.to_dict(), "issues": payload["issues"]})

    def play_trajectory(self) -> dict[str, Any]:
        state = self.simulation_service.play_trajectory()
        self._running = True
        self._publish("state", state.to_dict())
        self._publish("status", "running")
        return self.success({"state": state.to_dict()})

    def pause_trajectory(self) -> dict[str, Any]:
        self._running = False
        state = self.simulation_service.pause_trajectory()
        self._publish("state", state.to_dict())
        self._publish("status", "paused")
        return self.success({"state": state.to_dict()})

    def stop_trajectory(self) -> dict[str, Any]:
        self._running = False
        state = self.simulation_service.stop_trajectory()
        self._publish("state", state.to_dict())
        self._publish("status", "paused")
        return self.success({"state": state.to_dict()})

    def start_recording(self, scene_json: str, config_json: str) -> dict[str, Any]:
        scene = self._scene_from_json(scene_json)
        config = json.loads(config_json)
        if not isinstance(config, dict):
            raise ValueError("Recording config must be a JSON object")
        state = self.simulation_service.start_joint_recording(
            scene,
            name=str(config.get("name", "Joint Recording")),
            joint_ids=self._optional_string_list(config, "joint_ids"),
            actuator_ids=self._optional_string_list(config, "actuator_ids"),
            sensor_ids=self._optional_string_list(config, "sensor_ids"),
        )
        self._publish("state", state.to_dict())
        return self.success({"state": state.to_dict()})

    def stop_recording(self) -> dict[str, Any]:
        state, recording = self.simulation_service.stop_joint_recording()
        self._publish("state", state.to_dict())
        return self.success({"state": state.to_dict(), "recording": recording.to_dict()})

    def get_recording(self) -> dict[str, Any]:
        return self.success({"recording": self.simulation_service.get_joint_recording().to_dict()})

    def export_recording(self, path: str, format_name: str) -> dict[str, Any]:
        output = self.simulation_service.export_joint_recording(
            self._project_path(path), format_name
        )
        recording = self.simulation_service.get_joint_recording()
        return self.success({
            "path": str(output), "format": format_name, "sample_count": len(recording.samples)
        })

    def get_recording_export(self, format_name: str) -> dict[str, Any]:
        recording = self.simulation_service.get_joint_recording()
        if format_name == "json":
            content = json.dumps(recording.to_dict(), indent=2) + "\n"
        elif format_name == "csv":
            content = recording.to_csv()
        else:
            raise ValueError("Recording format must be 'json' or 'csv'")
        return self.success(
            {
                "path": f"joint-recording.{format_name}",
                "format": format_name,
                "sample_count": len(recording.samples),
                "content": content,
            }
        )

    def set_editor_state(self, scene_json: str, dirty: bool, current_path: str) -> dict[str, Any]:
        if scene_json != self.synced_scene_json and self.simulation_service.session is not None:
            self._stop_simulation()
        self.synced_scene_json = scene_json
        self.dirty = bool(dirty)
        self.current_path = Path(current_path) if current_path else None
        try:
            name = str(json.loads(scene_json).get("name", "Untitled Scene"))
        except (json.JSONDecodeError, AttributeError):
            name = "Untitled Scene"
        self._publish("title", self._title(name))
        return self.success()

    def events_since(self, sequence: int) -> list[dict[str, Any]]:
        with self._lock:
            return [event.copy() for event in self._events if event["sequence"] > sequence]

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            self._stop_simulation()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def advance_frame(self, *, force: bool = False) -> None:
        with self._lock:
            if not self._running and not force:
                return
            try:
                state = self.simulation_service.step_frame()
            except Exception as exc:
                self._running = False
                self._console(f"Simulation fault: {exc}")
                self._publish("status", "fault")
                return
            if state is None:
                self._running = False
                return
            payload = state.to_dict()
            self._publish("state", payload)
            if state.trajectory.status == "completed":
                self._running = False
                self._publish("status", "paused")

    @property
    def is_advancing(self) -> bool:
        with self._lock:
            return self._running

    def stop_simulation(self) -> None:
        with self._lock:
            self._stop_simulation()

    def _simulation_loop(self) -> None:
        while not self._closed.wait(0.016):
            self.advance_frame()

    def _stop_simulation(self) -> None:
        self._running = False
        self.simulation_service.stop()
        self._publish("status", "stopped")

    def _publish(self, event_type: str, payload: Any) -> None:
        self._event_sequence += 1
        self._events.append(
            {"sequence": self._event_sequence, "type": event_type, "payload": payload}
        )
        if len(self._events) > 512:
            del self._events[:-512]

    def _console(self, message: str) -> None:
        with self._lock:
            self._publish("console", message)

    def _scene_from_json(self, scene_json: str) -> Scene:
        data = json.loads(scene_json)
        if not isinstance(data, dict):
            raise ValueError("Scene payload must be a JSON object")
        scene = Scene.from_dict(data)
        validate_scene(scene)
        return scene

    @staticmethod
    def _optional_string_list(data: dict[str, Any], key: str) -> list[str] | None:
        value = data.get(key)
        if value is None:
            return None
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Recording {key} must be an array of strings")
        return value

    def _enrich_asset(self, source: dict[str, Any]) -> dict[str, Any]:
        asset = copy.deepcopy(source)
        properties = asset.get("default_properties")
        if not isinstance(properties, dict):
            return asset
        physics = properties.get("physics")
        if isinstance(physics, dict) and "material" in physics:
            values = material_for_id(physics["material"]).property_values()
            values.update(physics)
            properties["physics"] = values
        return asset

    @staticmethod
    def _safe_relative_path(raw_path: str) -> Path:
        normalized = raw_path.replace("\\", "/")
        path = Path(normalized)
        if (
            not normalized
            or normalized.startswith("/")
            or ":" in path.parts[0]
            or ".." in path.parts
            or path.is_absolute()
        ):
            raise ValueError(f"Unsafe uploaded path: {raw_path}")
        return path

    def _project_path(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        resolved = path.resolve() if path.is_absolute() else (self.project_root / path).resolve()
        if self._restrict_paths and not resolved.is_relative_to(self.project_root):
            raise ValueError("Web file access is restricted to the configured project root")
        return resolved

    @staticmethod
    def _preflight_payload(report: PhysicsPreflightReport) -> dict[str, Any]:
        return {"valid": report.is_valid, "issues": [asdict(issue) for issue in report.issues]}

    def _title(self, scene_name: str) -> str:
        dirty = "*" if self.dirty else ""
        path = f" - {self.current_path}" if self.current_path else ""
        return f"{dirty}SimLab - {scene_name}{path}"

    @staticmethod
    def success(data: Any = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": True}
        if data is not None:
            payload["data"] = data
        return payload

    @staticmethod
    def failure(error: object, data: Any = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": False, "error": str(error)}
        if data is not None:
            payload["data"] = data
        return payload
