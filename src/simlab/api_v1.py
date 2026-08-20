from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import Response
from pydantic import BaseModel, Field

from simlab.resources import ResourceManager
from simlab.services.openusd.upload_bundle import MAX_UPLOAD_BYTES, MAX_UPLOAD_FILES


class ProjectCreate(BaseModel):
    name: str = "Untitled Project"


class SimulationCreate(BaseModel):
    project_id: str


class SpeedUpdate(BaseModel):
    factor: float


class JointTargets(BaseModel):
    targets: dict[str, float]


class ActuatorControls(BaseModel):
    controls: dict[str, float]


class AttachmentCommands(BaseModel):
    commands: dict[str, bool]


class TrajectoryUpload(BaseModel):
    trajectory: dict[str, Any]


class RecordingStart(BaseModel):
    name: str = "Joint Recording"
    joint_ids: list[str] | None = None
    actuator_ids: list[str] | None = None
    sensor_ids: list[str] | None = None


class ControllerUpload(BaseModel):
    filename: str
    source: str


class OpenUsdUpload(BaseModel):
    files: list[dict[str, str]] = Field(min_length=1)
    entry: str
    package_entry: str | None = None


OPENUSD_REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["entry", "files"],
                    "properties": {
                        "entry": {"type": "string"},
                        "package_entry": {"type": "string", "nullable": True},
                        "files": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                        },
                    },
                }
            },
            "application/json": {"schema": OpenUsdUpload.model_json_schema()},
        },
    }
}


def create_v1_router(manager: ResourceManager, access_token: str | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    async def authorize(authorization: str | None = Header(default=None)) -> None:
        if access_token is None:
            return
        if authorization != f"Bearer {access_token}":
            raise HTTPException(status_code=401, detail="Invalid access token")

    auth = Depends(authorize)

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {"version": "v1", "status": "ok"}

    @router.post("/projects", dependencies=[auth], status_code=201)
    async def create_project(request: ProjectCreate) -> dict[str, Any]:
        project = manager.create_project(request.name)
        return project_payload(project)

    @router.get("/projects/{project_id}", dependencies=[auth])
    async def get_project(project_id: str) -> dict[str, Any]:
        return project_payload(manager.get_project(project_id))

    @router.put("/projects/{project_id}/scene", dependencies=[auth])
    async def update_scene(project_id: str, scene: dict[str, Any]) -> dict[str, Any]:
        project = manager.update_scene(project_id, scene)
        return project_payload(project)

    @router.get("/projects/{project_id}/assets", dependencies=[auth])
    async def assets(project_id: str) -> dict[str, Any]:
        return {"version": "v1", "assets": manager.assets(project_id)}

    @router.post(
        "/projects/{project_id}/assets/openusd",
        dependencies=[auth],
        status_code=201,
        openapi_extra=OPENUSD_REQUEST_BODY,
    )
    async def import_openusd(
        project_id: str, request: Request
    ) -> dict[str, Any]:
        content_type = request.headers.get("content-type", "").lower()
        if content_type.startswith("multipart/form-data"):
            async with request.form(
                max_files=MAX_UPLOAD_FILES,
                max_fields=32,
                max_part_size=MAX_UPLOAD_BYTES,
            ) as form:
                entry = form.get("entry")
                package_entry = form.get("package_entry")
                if not isinstance(entry, str) or not entry:
                    raise HTTPException(status_code=422, detail="OpenUSD entry is required")
                if package_entry is not None and not isinstance(package_entry, str):
                    raise HTTPException(
                        status_code=422,
                        detail="OpenUSD package_entry must be a string",
                    )
                uploads = [
                    item
                    for item in form.getlist("files")
                    if hasattr(item, "filename") and hasattr(item, "file")
                ]
                if not uploads:
                    raise HTTPException(status_code=422, detail="OpenUSD files are required")
                streams = [
                    (str(item.filename or ""), item.file)
                    for item in uploads
                ]
                data = manager.import_openusd_streams(
                    project_id,
                    streams,
                    entry,
                    package_entry,
                )
        elif content_type.startswith("application/json"):
            upload = OpenUsdUpload.model_validate(await request.json())
            data = manager.import_openusd(
                project_id,
                json.dumps(upload.files),
                upload.entry,
                upload.package_entry,
            )
        else:
            raise HTTPException(
                status_code=415,
                detail="OpenUSD upload must use multipart/form-data or application/json",
            )
        return {"version": "v1", **data}

    @router.get(
        "/projects/{project_id}/geometry/{artifact_id}", dependencies=[auth]
    )
    async def visual_geometry(project_id: str, artifact_id: str) -> dict[str, Any]:
        return manager.visual_geometry(project_id, artifact_id)

    @router.post(
        "/projects/{project_id}/exports/mjcf", dependencies=[auth], status_code=201
    )
    async def export_mjcf(project_id: str) -> dict[str, Any]:
        data, artifact = manager.export_mjcf(project_id)
        return {
            "version": "v1",
            "artifact": artifact_payload(artifact),
            "issues": data.get("issues", []),
        }

    @router.post("/projects/{project_id}/preflight", dependencies=[auth])
    async def preflight(project_id: str) -> dict[str, Any]:
        return {"version": "v1", **manager.preflight(project_id)}

    @router.post("/simulations", dependencies=[auth], status_code=201)
    async def create_simulation(request: SimulationCreate) -> dict[str, Any]:
        simulation = manager.create_simulation(request.project_id)
        return {
            "version": "v1",
            "id": simulation.id,
            "project_id": simulation.project_id,
            "snapshot": manager.snapshot(simulation.id),
        }

    @router.delete("/simulations/{simulation_id}", dependencies=[auth], status_code=204)
    async def delete_simulation(simulation_id: str) -> Response:
        manager.delete_simulation(simulation_id)
        return Response(status_code=204)

    @router.get("/simulations/{simulation_id}/snapshot", dependencies=[auth])
    async def snapshot(simulation_id: str) -> dict[str, Any]:
        return {"version": "v1", **manager.snapshot(simulation_id)}

    @router.post("/simulations/{simulation_id}/run", dependencies=[auth])
    async def run(simulation_id: str) -> dict[str, Any]:
        scene_json = manager.simulation_scene_json(simulation_id)
        return envelope(manager.call_simulation(simulation_id, "runSimulation", [scene_json]))

    @router.post("/simulations/{simulation_id}/pause", dependencies=[auth])
    async def pause(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "pauseSimulation", []))

    @router.post("/simulations/{simulation_id}/step", dependencies=[auth])
    async def step(simulation_id: str) -> dict[str, Any]:
        scene_json = manager.simulation_scene_json(simulation_id)
        return envelope(manager.call_simulation(simulation_id, "stepSimulation", [scene_json]))

    @router.post("/simulations/{simulation_id}/reset", dependencies=[auth])
    async def reset(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "resetSimulation", []))

    @router.put("/simulations/{simulation_id}/speed", dependencies=[auth])
    async def speed(simulation_id: str, request: SpeedUpdate) -> dict[str, Any]:
        return envelope(
            manager.call_simulation(
                simulation_id, "setSimulationSpeed", [request.factor]
            )
        )

    @router.put("/simulations/{simulation_id}/joint-targets", dependencies=[auth])
    async def joint_targets(
        simulation_id: str, request: JointTargets
    ) -> dict[str, Any]:
        return envelope(manager.set_joint_targets(simulation_id, request.targets))

    @router.put("/simulations/{simulation_id}/actuator-controls", dependencies=[auth])
    async def actuator_controls(
        simulation_id: str, request: ActuatorControls
    ) -> dict[str, Any]:
        return envelope(manager.set_actuator_controls(simulation_id, request.controls))

    @router.put("/simulations/{simulation_id}/attachments", dependencies=[auth])
    async def attachment_commands(
        simulation_id: str, request: AttachmentCommands
    ) -> dict[str, Any]:
        return envelope(manager.set_attachment_commands(simulation_id, request.commands))

    @router.put("/simulations/{simulation_id}/trajectory", dependencies=[auth])
    async def load_trajectory(
        simulation_id: str, request: TrajectoryUpload
    ) -> dict[str, Any]:
        return envelope(manager.load_trajectory(simulation_id, request.trajectory))

    @router.post("/simulations/{simulation_id}/trajectory/play", dependencies=[auth])
    async def play_trajectory(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "playTrajectory", []))

    @router.post("/simulations/{simulation_id}/trajectory/pause", dependencies=[auth])
    async def pause_trajectory(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "pauseTrajectory", []))

    @router.post("/simulations/{simulation_id}/trajectory/stop", dependencies=[auth])
    async def stop_trajectory(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "stopTrajectory", []))

    @router.post("/simulations/{simulation_id}/recordings", dependencies=[auth])
    async def start_recording(
        simulation_id: str, request: RecordingStart
    ) -> dict[str, Any]:
        return envelope(manager.start_recording(simulation_id, request.model_dump()))

    @router.post("/simulations/{simulation_id}/recordings/stop", dependencies=[auth])
    async def stop_recording(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "stopRecording", []))

    @router.get("/simulations/{simulation_id}/recordings/current", dependencies=[auth])
    async def current_recording(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "getRecording", []))

    @router.post(
        "/simulations/{simulation_id}/recordings/{format_name}/artifact",
        dependencies=[auth],
        status_code=201,
    )
    async def recording_artifact(
        simulation_id: str, format_name: str
    ) -> dict[str, Any]:
        data, artifact = manager.recording_artifact(simulation_id, format_name)
        return {
            "version": "v1",
            "artifact": artifact_payload(artifact),
            "sample_count": data["sample_count"],
            "format": data["format"],
        }

    @router.post("/simulations/{simulation_id}/controller", dependencies=[auth])
    async def load_controller(
        simulation_id: str, request: ControllerUpload
    ) -> dict[str, Any]:
        return envelope(
            manager.load_controller(simulation_id, request.filename, request.source)
        )

    @router.delete("/simulations/{simulation_id}/controller", dependencies=[auth])
    async def detach_controller(simulation_id: str) -> dict[str, Any]:
        return envelope(manager.call_simulation(simulation_id, "detachController", []))

    @router.get("/artifacts/{artifact_id}", dependencies=[auth])
    async def download_artifact(artifact_id: str, request: Request) -> Response:
        artifact = manager.get_artifact(artifact_id)
        etag = f'"{artifact.id}"'
        cache_control = (
            "private, max-age=31536000, immutable"
            if artifact.filename.endswith(".simbin")
            else "private, max-age=0, must-revalidate"
        )
        headers = {
            "Content-Disposition": f'inline; filename="{artifact.filename}"',
            "Content-Encoding": "identity",
            "X-SimLab-Artifact-Id": artifact.id,
            "Cache-Control": cache_control,
            "ETag": etag,
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        if artifact.content is None:
            path = manager.artifact_path(artifact_id)
            return Response(
                content=path.read_bytes(),
                media_type=artifact.media_type,
                headers=headers,
            )
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers=headers,
        )

    @router.websocket("/simulations/{simulation_id}/events")
    async def events(
        websocket: WebSocket,
        simulation_id: str,
        after_sequence: int = Query(default=0, ge=0),
        token: str | None = Query(default=None),
    ) -> None:
        if access_token is not None and token != access_token:
            await websocket.accept()
            await websocket.close(code=4401, reason="Invalid access token")
            return
        simulation = manager.get_simulation(simulation_id)
        await websocket.accept()
        manager.register_subscriber(simulation_id)
        snapshot_data = manager.snapshot(simulation_id)
        latest = int(snapshot_data["sequence"])
        if after_sequence == 0 or latest - after_sequence > 512:
            await websocket.send_json(
                {
                    "version": "v1",
                    "simulation_id": simulation_id,
                    "sequence": latest,
                    "type": "snapshot",
                    "payload": snapshot_data,
                }
            )
            after_sequence = latest
        last_heartbeat = time.monotonic()
        try:
            while True:
                emitted = False
                for event in simulation.application.events_since(after_sequence):
                    await websocket.send_json(
                        {
                            "version": "v1",
                            "simulation_id": simulation_id,
                            **event,
                        }
                    )
                    after_sequence = int(event["sequence"])
                    emitted = True
                now = time.monotonic()
                if not emitted and now - last_heartbeat >= 5.0:
                    await websocket.send_json(
                        {
                            "version": "v1",
                            "simulation_id": simulation_id,
                            "sequence": after_sequence,
                            "type": "heartbeat",
                            "payload": None,
                        }
                    )
                    last_heartbeat = now
                await asyncio.sleep(0.016)
        except Exception:
            pass
        finally:
            manager.unregister_subscriber(simulation_id)

    return router


def envelope(result: dict[str, Any]) -> dict[str, Any]:
    return {"version": "v1", **result}


def project_payload(project: Any) -> dict[str, Any]:
    return {
        "version": "v1",
        "id": project.id,
        "name": project.name,
        "revision": project.revision,
        "scene": project.scene,
    }


def artifact_payload(artifact: Any) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "filename": artifact.filename,
        "media_type": artifact.media_type,
        "download_url": f"/api/v1/artifacts/{artifact.id}",
    }
