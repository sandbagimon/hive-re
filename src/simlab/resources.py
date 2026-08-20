from __future__ import annotations

import copy
import hashlib
import json
import mimetypes
import os
import shutil
import threading
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from simlab.models.scene import Scene
from simlab.services.local_scene_streaming import LocalSceneService
from simlab.services.project_service import validate_scene
from simlab.web_application import WebApplication

REFERENCE_FIELDS = {
    "source",
    "visual_cache",
    "visual_bundle",
    "collision_mesh",
    "robotics_cache",
    "import_report",
    "manifest",
    "base_color_texture",
    "normal_texture",
    "roughness_texture",
    "metallic_texture",
}

_FICLONE = 0x40049409


def _clone_or_copy(source: str, destination: str) -> str:
    """Use CoW cloning, then hard-link immutable caches, then fall back to copying."""
    try:
        import fcntl

        with open(source, "rb") as source_file, open(destination, "xb") as target_file:
            fcntl.ioctl(target_file.fileno(), _FICLONE, source_file.fileno())
        shutil.copystat(source, destination)
        return destination
    except (ImportError, OSError):
        try:
            os.unlink(destination)
        except FileNotFoundError:
            pass
        try:
            os.link(source, destination)
            return destination
        except OSError:
            return shutil.copy2(source, destination)


class ResourceValidationError(ValueError):
    def __init__(self, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.data = data


def _rebind_reference_fields(value: Any, canonical: Any) -> Any:
    """Replace transport-scoped resource IDs with this project's catalog refs."""

    if isinstance(value, list):
        if not isinstance(canonical, list):
            return copy.deepcopy(value)
        canonical_by_id = {
            item["id"]: item
            for item in canonical
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        list_output: list[Any] = []
        for index, item in enumerate(value):
            canonical_item = canonical[index] if index < len(canonical) else None
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                canonical_item = canonical_by_id.get(item["id"], canonical_item)
            list_output.append(_rebind_reference_fields(item, canonical_item))
        return list_output
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    canonical_dict = canonical if isinstance(canonical, dict) else {}
    dict_output: dict[str, Any] = {}
    for key, item in value.items():
        canonical_item = canonical_dict.get(key)
        if key in REFERENCE_FIELDS and isinstance(canonical_item, str):
            dict_output[key] = canonical_item
        else:
            dict_output[key] = _rebind_reference_fields(item, canonical_item)
    return dict_output


@dataclass(slots=True)
class ProjectResource:
    id: str
    name: str
    root: Path
    scene: dict[str, Any]
    revision: int = 0


@dataclass(slots=True)
class SimulationResource:
    id: str
    project_id: str
    application: WebApplication
    scene_json: str
    subscribers: int = 0


@dataclass(slots=True)
class ArtifactResource:
    id: str
    project_id: str
    filename: str
    media_type: str
    content: bytes | None = None
    reference: str | None = None


class ResourceManager:
    """Own independent project, simulation, and artifact resources."""

    def __init__(
        self,
        data_root: Path,
        seed_assets: Path,
        *,
        allow_controller_execution: bool = False,
        local_scene_root: Path | None = None,
    ) -> None:
        self.data_root = data_root.resolve()
        self.seed_assets = seed_assets.resolve()
        self.allow_controller_execution = allow_controller_execution
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.projects: dict[str, ProjectResource] = {}
        self.simulations: dict[str, SimulationResource] = {}
        self.artifacts: dict[str, ArtifactResource] = {}
        self.local_scenes = LocalSceneService(self.data_root, local_scene_root)

    def create_project(self, name: str = "Untitled Project") -> ProjectResource:
        with self._lock:
            project_id = f"prj_{uuid.uuid4().hex}"
            root = self.data_root / "projects" / project_id
            root.mkdir(parents=True)
            if self.seed_assets.exists():
                shutil.copytree(
                    self.seed_assets,
                    root / "assets",
                    copy_function=_clone_or_copy,
                    ignore=shutil.ignore_patterns("external"),
                )
            else:
                (root / "assets").mkdir()
                (root / "assets" / "metadata.json").write_text(
                    '{"assets": []}\n', encoding="utf-8"
                )
            scene = Scene(name=name).to_dict()
            project = ProjectResource(project_id, name, root, scene)
            self.projects[project_id] = project
            return project

    def get_project(self, project_id: str) -> ProjectResource:
        try:
            return self.projects[project_id]
        except KeyError as exc:
            raise KeyError(f"Unknown project: {project_id}") from exc

    def update_scene(self, project_id: str, scene: dict[str, Any]) -> ProjectResource:
        with self._lock:
            project = self.get_project(project_id)
            rebound = self._rebind_catalog_references(project, scene)
            external = self.externalize(project, rebound)
            hydrated = self.hydrate(project, external)
            model = Scene.from_dict(hydrated)
            validate_scene(model)
            canonical = model.to_dict()
            project.scene = self.externalize(project, canonical)
            project.name = model.name
            project.revision += 1
            return project

    def _rebind_catalog_references(
        self, project: ProjectResource, scene: dict[str, Any]
    ) -> dict[str, Any]:
        """Make a browser-saved catalog scene portable across project IDs."""

        rebound = copy.deepcopy(scene)
        actors = rebound.get("actors")
        if not isinstance(actors, list) or not actors:
            return rebound
        metadata_path = project.root / "assets" / "metadata.json"
        if not metadata_path.is_file():
            return rebound
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        raw_assets = metadata.get("assets") if isinstance(metadata, dict) else None
        if not isinstance(raw_assets, list):
            return rebound
        assets = {
            item["id"]: item
            for item in raw_assets
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        local_asset = self.local_scenes.asset(project.root)
        if local_asset is not None:
            assets[local_asset["id"]] = local_asset
        canonical_articulations: dict[str, dict[str, Any]] = {}
        for actor in actors:
            if not isinstance(actor, dict):
                continue
            asset_id = actor.get("asset_id")
            asset = assets.get(asset_id) if isinstance(asset_id, str) else None
            if not isinstance(asset, dict):
                continue
            canonical_properties = asset.get("default_properties")
            if isinstance(actor.get("properties"), dict) and isinstance(
                canonical_properties, dict
            ):
                actor["properties"] = _rebind_reference_fields(
                    actor["properties"], canonical_properties
                )
            robotics_cache = (
                canonical_properties.get("robotics_cache")
                if isinstance(canonical_properties, dict)
                else None
            )
            if not isinstance(robotics_cache, str):
                continue
            robotics_path = (project.root / robotics_cache).resolve()
            if not robotics_path.is_relative_to(project.root) or not robotics_path.is_file():
                continue
            cached_robotics = json.loads(robotics_path.read_text(encoding="utf-8"))
            articulations = (
                cached_robotics.get("articulations")
                if isinstance(cached_robotics, dict)
                else None
            )
            if not isinstance(articulations, list):
                continue
            canonical_articulations.update(
                {
                    item["id"]: item
                    for item in articulations
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                }
            )
        scene_robotics = rebound.get("robotics")
        if not isinstance(scene_robotics, dict):
            return rebound
        articulations = scene_robotics.get("articulations")
        if isinstance(articulations, list):
            rebound_articulations: list[Any] = []
            for articulation in articulations:
                articulation_id = (
                    articulation.get("id") if isinstance(articulation, dict) else None
                )
                canonical = (
                    canonical_articulations.get(articulation_id)
                    if isinstance(articulation_id, str)
                    else None
                )
                rebound_articulations.append(
                    _rebind_reference_fields(articulation, canonical)
                )
            scene_robotics["articulations"] = rebound_articulations
        return rebound

    def assets(self, project_id: str) -> list[dict[str, Any]]:
        project = self.get_project(project_id)
        app = WebApplication(project.root, background_simulation=False)
        try:
            result = app.dispatch("getAssets", [])
        finally:
            app.close()
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error")))
        assets = [self.externalize(project, item) for item in result["data"]["assets"]]
        local_asset = self.local_scenes.asset(project.root)
        if local_asset is not None:
            assets.append(self.externalize(project, local_asset))
        return assets

    def local_scene_statuses(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        return self.local_scenes.statuses()

    def local_scene_manifest(self, project_id: str, scene_id: str) -> dict[str, Any]:
        self.get_project(project_id)
        return self.local_scenes.manifest(scene_id)

    def local_scene_chunk_path(
        self, project_id: str, scene_id: str, chunk_id: str
    ) -> Path:
        self.get_project(project_id)
        return self.local_scenes.chunk_path(scene_id, chunk_id)

    def import_openusd(
        self,
        project_id: str,
        bundle_json: str,
        entry_name: str,
        package_entry: str | None = None,
    ) -> dict[str, Any]:
        project = self.get_project(project_id)
        app = WebApplication(project.root, background_simulation=False)
        try:
            result = app.dispatch(
                "importOpenUsdBundle",
                [bundle_json, entry_name, package_entry],
            )
        finally:
            app.close()
        if not result.get("ok"):
            raise ResourceValidationError(
                str(result.get("error")), result.get("data")
            )
        return self.externalize(project, result["data"])

    def import_openusd_streams(
        self,
        project_id: str,
        files: Iterable[tuple[str, BinaryIO]],
        entry_name: str,
        package_entry: str | None = None,
    ) -> dict[str, Any]:
        project = self.get_project(project_id)
        app = WebApplication(project.root, background_simulation=False)
        try:
            result = app.import_openusd_streams(files, entry_name, package_entry)
        except Exception as exc:
            data = getattr(getattr(exc, "report", None), "to_dict", lambda: None)()
            raise ResourceValidationError(str(exc), data) from exc
        finally:
            app.close()
        if not result.get("ok"):
            raise ResourceValidationError(
                str(result.get("error")), result.get("data")
            )
        return self.externalize(project, result["data"])

    def visual_geometry(self, project_id: str, artifact_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        artifact = self.get_artifact(artifact_id, project_id)
        if artifact.reference is None:
            raise ValueError("Artifact is not visual geometry")
        app = WebApplication(project.root, background_simulation=False)
        try:
            result = app.dispatch("getVisualGeometry", [artifact.reference])
        finally:
            app.close()
        if not result.get("ok"):
            raise ValueError(str(result.get("error")))
        return self.externalize(project, result["data"])

    def export_mjcf(self, project_id: str) -> tuple[dict[str, Any], ArtifactResource]:
        project = self.get_project(project_id)
        app = WebApplication(project.root, background_simulation=False)
        try:
            hydrated = self.hydrate(project, project.scene)
            result = app.dispatch("exportMjcf", [json.dumps(hydrated)])
        finally:
            app.close()
        if not result.get("ok"):
            raise ResourceValidationError(
                str(result.get("error")), result.get("data")
            )
        data = result["data"]
        artifact = self.create_artifact(
            project_id,
            str(data.get("filename", "scene.xml")),
            "application/xml",
            str(data["content"]).encode(),
        )
        return data, artifact

    def preflight(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        app = WebApplication(project.root, background_simulation=False)
        try:
            hydrated = self.hydrate(project, project.scene)
            result = app.dispatch("preflight", [json.dumps(hydrated)])
        finally:
            app.close()
        if not result.get("ok"):
            raise ValueError(str(result.get("error")))
        return result["data"]

    def create_simulation(self, project_id: str) -> SimulationResource:
        with self._lock:
            project = self.get_project(project_id)
            simulation_id = f"sim_{uuid.uuid4().hex}"
            external_json = json.dumps(project.scene, sort_keys=True)
            app = WebApplication(project.root)
            simulation = SimulationResource(
                simulation_id, project_id, app, external_json
            )
            self.simulations[simulation_id] = simulation
            return simulation

    def get_simulation(self, simulation_id: str) -> SimulationResource:
        try:
            return self.simulations[simulation_id]
        except KeyError as exc:
            raise KeyError(f"Unknown simulation: {simulation_id}") from exc

    def register_subscriber(self, simulation_id: str) -> None:
        with self._lock:
            simulation = self.get_simulation(simulation_id)
            simulation.subscribers += 1

    def unregister_subscriber(self, simulation_id: str) -> None:
        with self._lock:
            try:
                simulation = self.get_simulation(simulation_id)
            except KeyError:
                return
            simulation.subscribers = max(0, simulation.subscribers - 1)
            if simulation.subscribers == 0:
                simulation.application.pause_if_running()

    def delete_simulation(self, simulation_id: str) -> None:
        with self._lock:
            simulation = self.get_simulation(simulation_id)
            simulation.application.close()
            del self.simulations[simulation_id]

    def call_simulation(
        self, simulation_id: str, method: str, args: list[Any]
    ) -> dict[str, Any]:
        simulation = self.get_simulation(simulation_id)
        project = self.get_project(simulation.project_id)
        hydrated_args = [self.hydrate(project, item) for item in args]
        hydrated_args = [
            json.dumps(item) if isinstance(original, str) and isinstance(item, dict) else item
            for original, item in zip(args, hydrated_args, strict=True)
        ]
        return simulation.application.dispatch(method, hydrated_args)

    def simulation_scene_json(self, simulation_id: str) -> str:
        simulation = self.get_simulation(simulation_id)
        project = self.get_project(simulation.project_id)
        snapshot = json.loads(simulation.scene_json)
        return json.dumps(self.hydrate(project, snapshot))

    def snapshot(self, simulation_id: str) -> dict[str, Any]:
        simulation = self.get_simulation(simulation_id)
        session = simulation.application.simulation_service.session
        state = session.state().to_dict() if session is not None else None
        status = (
            "running"
            if simulation.application.is_advancing
            else "paused" if session is not None else "stopped"
        )
        events = simulation.application.events_since(0)
        sequence = int(events[-1]["sequence"]) if events else 0
        return {"sequence": sequence, "status": status, "state": state}

    def start_recording(
        self, simulation_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        scene_json = self.simulation_scene_json(simulation_id)
        return self.call_simulation(
            simulation_id, "startRecording", [scene_json, json.dumps(config)]
        )

    def load_trajectory(
        self, simulation_id: str, trajectory: dict[str, Any]
    ) -> dict[str, Any]:
        scene_json = self.simulation_scene_json(simulation_id)
        return self.call_simulation(
            simulation_id, "loadTrajectory", [scene_json, json.dumps(trajectory)]
        )

    def set_joint_targets(
        self, simulation_id: str, targets: dict[str, float]
    ) -> dict[str, Any]:
        scene_json = self.simulation_scene_json(simulation_id)
        return self.call_simulation(
            simulation_id, "setJointTargets", [scene_json, json.dumps(targets)]
        )

    def set_actuator_controls(
        self, simulation_id: str, controls: dict[str, float]
    ) -> dict[str, Any]:
        scene_json = self.simulation_scene_json(simulation_id)
        return self.call_simulation(
            simulation_id, "setActuatorControls", [scene_json, json.dumps(controls)]
        )

    def set_attachment_commands(
        self, simulation_id: str, commands: dict[str, bool]
    ) -> dict[str, Any]:
        scene_json = self.simulation_scene_json(simulation_id)
        return self.call_simulation(
            simulation_id, "setAttachmentCommands", [scene_json, json.dumps(commands)]
        )

    def load_controller(
        self, simulation_id: str, filename: str, source: str
    ) -> dict[str, Any]:
        if not self.allow_controller_execution:
            raise PermissionError(
                "Controller execution is disabled; start the trusted backend with "
                "--allow-controller-execution"
            )
        scene_json = self.simulation_scene_json(simulation_id)
        result = self.call_simulation(
            simulation_id,
            "loadControllerContent",
            [scene_json, filename, source],
        )
        controller = result.get("data", {}).get("controller")
        if isinstance(controller, dict):
            controller["path"] = Path(filename).name
        return result

    def recording_artifact(
        self, simulation_id: str, format_name: str
    ) -> tuple[dict[str, Any], ArtifactResource]:
        simulation = self.get_simulation(simulation_id)
        result = simulation.application.dispatch("getRecordingExport", [format_name])
        if not result.get("ok"):
            raise ValueError(str(result.get("error")))
        data = result["data"]
        media_type = "application/json" if format_name == "json" else "text/csv"
        artifact = self.create_artifact(
            simulation.project_id,
            str(data["path"]),
            media_type,
            str(data["content"]).encode(),
        )
        return data, artifact

    def create_artifact(
        self,
        project_id: str,
        filename: str,
        media_type: str,
        content: bytes | None = None,
        reference: str | None = None,
    ) -> ArtifactResource:
        seed = f"{project_id}:{reference}" if reference else uuid.uuid4().hex
        artifact_id = f"art_{hashlib.sha256(seed.encode()).hexdigest()[:24]}"
        artifact = ArtifactResource(
            artifact_id, project_id, filename, media_type, content, reference
        )
        self.artifacts[artifact_id] = artifact
        return artifact

    def get_artifact(
        self, artifact_id: str, project_id: str | None = None
    ) -> ArtifactResource:
        try:
            artifact = self.artifacts[artifact_id]
        except KeyError as exc:
            raise KeyError(f"Unknown artifact: {artifact_id}") from exc
        if project_id is not None and artifact.project_id != project_id:
            raise PermissionError("Artifact does not belong to this project")
        return artifact

    def artifact_path(self, artifact_id: str) -> Path:
        artifact = self.get_artifact(artifact_id)
        if artifact.reference is None:
            raise ValueError("Artifact is not file-backed")
        project = self.get_project(artifact.project_id)
        path = (project.root / artifact.reference).resolve()
        if not path.is_relative_to(project.root) or not path.is_file():
            raise ValueError("Artifact file is unavailable")
        return path

    def externalize(self, project: ProjectResource, value: Any) -> Any:
        if isinstance(value, list):
            return [self.externalize(project, item) for item in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        output: dict[str, Any] = {}
        for key, item in value.items():
            if key in REFERENCE_FIELDS and isinstance(item, str):
                path = (project.root / item).resolve()
                if path.is_relative_to(project.root) and path.exists():
                    artifact = self.create_artifact(
                        project.id,
                        path.name,
                        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                        reference=item,
                    )
                    output[key] = artifact.id
                    continue
            output[key] = self.externalize(project, item)
        return output

    def hydrate(self, project: ProjectResource, value: Any) -> Any:
        if isinstance(value, list):
            return [self.hydrate(project, item) for item in value]
        if isinstance(value, dict):
            return {key: self.hydrate(project, item) for key, item in value.items()}
        if isinstance(value, str) and value.startswith("art_"):
            artifact = self.artifacts.get(value)
            if artifact and artifact.project_id == project.id and artifact.reference:
                return artifact.reference
        return copy.deepcopy(value)

    def close(self) -> None:
        with self._lock:
            simulations = list(self.simulations.values())
            self.simulations.clear()
        for simulation in simulations:
            simulation.application.close()
