import asyncio
import base64
import json
from pathlib import Path

import httpx

from simlab.models.actor import Actor
from simlab.models.robotics import RoboticsModel, Sensor
from simlab.models.scene import Scene
from simlab.services.project_service import load_scene
from simlab.web_application import WebApplication
from simlab.web_server import create_app


def test_web_application_saves_and_opens_without_qt(tmp_path: Path) -> None:
    application = WebApplication(tmp_path)
    scene = Scene(name="Browser Scene")
    path = tmp_path / "projects" / "browser.json"
    try:
        saved = application.dispatch(
            "saveProjectPath", [json.dumps(scene.to_dict()), str(path)]
        )
        opened = application.dispatch("openProjectPath", [str(path)])
    finally:
        application.close()

    assert saved == {"ok": True, "data": {"path": str(path)}}
    assert opened["ok"] is True
    assert opened["data"]["scene"] == scene.to_dict()


def test_web_application_opens_browser_content_and_restricts_server_paths(
    tmp_path: Path,
) -> None:
    application = WebApplication(tmp_path)
    scene = Scene(name="Uploaded Scene")
    try:
        opened = application.dispatch(
            "openProjectContent", [json.dumps(scene.to_dict()), "uploaded.json"]
        )
        escaped = application.dispatch(
            "saveProjectPath",
            [json.dumps(scene.to_dict()), str(tmp_path.parent / "escaped.json")],
        )
    finally:
        application.close()

    assert opened["ok"] is True
    assert opened["data"]["path"] == "uploaded.json"
    assert escaped["ok"] is False
    assert "restricted" in escaped["error"]


def test_web_application_imports_uploaded_openusd_bundle(tmp_path: Path) -> None:
    source = Path("tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda")
    bundle = [
        {
            "name": source.name,
            "content": base64.b64encode(source.read_bytes()).decode("ascii"),
        }
    ]
    application = WebApplication(tmp_path, background_simulation=False)
    try:
        imported = application.dispatch(
            "importOpenUsdBundle", [json.dumps(bundle), source.name]
        )
        unsafe = application.dispatch(
            "importOpenUsdBundle",
            [json.dumps([{"name": "../bad.usda", "content": ""}]), "../bad.usda"],
        )
        robotics = RoboticsModel.from_dict(imported["data"]["robotics"])
        articulation = robotics.articulations[0]
        articulation.sensors.append(
            Sensor(
                id="web_joint_sensor",
                name="Web Joint Sensor",
                sensor_type="joint_state",
                joint_id=articulation.joints[0].id,
                update_rate_hz=100.0,
            )
        )
        asset = imported["data"]["asset"]
        scene = Scene(
            actors=[
                Actor(
                    id="web_robot",
                    name="Web Robot",
                    type="robot",
                    asset_id=asset["id"],
                    properties=asset["default_properties"],
                )
            ],
            robotics=robotics,
        )
        run = application.dispatch("runSimulation", [json.dumps(scene.to_dict())])
        application.advance_frame(force=True)
        state_events = [
            event for event in application.events_since(0) if event["type"] == "state"
        ]
    finally:
        application.close()

    assert imported["ok"] is True
    assert imported["data"]["asset"]["type"] == "robot"
    assert unsafe["ok"] is False
    assert "Unsafe uploaded path" in unsafe["error"]
    assert run["data"]["state"]["sensors"][0]["id"] == "web_joint_sensor"
    assert state_events[-1]["payload"]["sensors"][0]["id"] == "web_joint_sensor"


def request(app: object, method: str, path: str, **kwargs: object) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def create_api_project(app: object, name: str = "API Project") -> str:
    response = request(app, "POST", "/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    project_id = response.json()["id"]
    assert project_id.startswith("prj_")
    return str(project_id)


def test_web_server_exposes_only_versioned_backend_resources(tmp_path: Path) -> None:
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    route_paths = {route.path for route in app.routes}
    try:
        health = request(app, "GET", "/api/v1/health")
        frontend = request(app, "GET", "/")
        legacy_rpc = request(app, "POST", "/api/rpc/getAssets", json={"args": []})
        project_id = create_api_project(app)
        assets = request(app, "GET", f"/api/v1/projects/{project_id}/assets")
    finally:
        app.state.resources.close()

    assert health.status_code == 200
    assert health.json() == {"version": "v1", "status": "ok"}
    assert all(path.startswith("/api/") for path in route_paths)
    assert "/redoc" not in route_paths
    assert frontend.status_code == 404
    assert legacy_rpc.status_code == 404
    assert assets.status_code == 200
    assert assets.json()["version"] == "v1"
    assert assets.json()["assets"]


def test_versioned_api_runs_isolated_simulation_resources(tmp_path: Path) -> None:
    scene = load_scene("examples/demo_project/scene.json")
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    try:
        project_a = create_api_project(app, "A")
        project_b = create_api_project(app, "B")
        for project_id in (project_a, project_b):
            updated = request(
                app,
                "PUT",
                f"/api/v1/projects/{project_id}/scene",
                json=scene.to_dict(),
            )
            assert updated.status_code == 200
        simulation_a = request(
            app,
            "POST",
            "/api/v1/simulations",
            json={"project_id": project_a},
        ).json()["id"]
        simulation_b = request(
            app,
            "POST",
            "/api/v1/simulations",
            json={"project_id": project_b},
        ).json()["id"]
        run = request(app, "POST", f"/api/v1/simulations/{simulation_a}/run").json()
        untouched = request(
            app, "GET", f"/api/v1/simulations/{simulation_b}/snapshot"
        ).json()
        pause = request(
            app, "POST", f"/api/v1/simulations/{simulation_a}/pause"
        ).json()
        reset = request(
            app, "POST", f"/api/v1/simulations/{simulation_a}/reset"
        ).json()
    finally:
        app.state.resources.close()

    assert run["ok"] is True
    assert run["data"]["state"]["time"] == 0
    assert untouched["status"] == "stopped"
    assert untouched["state"] is None
    assert pause["ok"] is True
    assert reset["ok"] is True
    assert reset["data"]["state"]["time"] == 0


def test_api_exports_downloadable_artifacts_without_server_paths(tmp_path: Path) -> None:
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    try:
        project_id = create_api_project(app)
        scene = load_scene("examples/demo_project/scene.json")
        request(
            app,
            "PUT",
            f"/api/v1/projects/{project_id}/scene",
            json=scene.to_dict(),
        )
        exported = request(
            app, "POST", f"/api/v1/projects/{project_id}/exports/mjcf"
        )
        artifact = exported.json()["artifact"]
        downloaded = request(app, "GET", artifact["download_url"])
    finally:
        app.state.resources.close()

    assert exported.status_code == 201
    assert artifact["id"].startswith("art_")
    assert artifact["download_url"] == f"/api/v1/artifacts/{artifact['id']}"
    assert "/" not in artifact["filename"]
    assert downloaded.status_code == 200
    assert downloaded.headers["x-simlab-artifact-id"] == artifact["id"]
    assert b"<mujoco" in downloaded.content


def test_api_enforces_token_cors_and_controller_boundary(tmp_path: Path) -> None:
    origin = "https://frontend.example"
    app = create_app(
        tmp_path,
        seed_assets=Path.cwd() / "assets",
        cors_origins=[origin],
        access_token="test-token",
    )
    auth = {"Authorization": "Bearer test-token"}
    try:
        denied = request(app, "POST", "/api/v1/projects", json={})
        preflight = request(
            app,
            "OPTIONS",
            "/api/v1/projects",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        rejected_origin = request(
            app,
            "OPTIONS",
            "/api/v1/projects",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        created = request(
            app, "POST", "/api/v1/projects", headers=auth, json={"name": "Secure"}
        )
        simulation = request(
            app,
            "POST",
            "/api/v1/simulations",
            headers=auth,
            json={"project_id": created.json()["id"]},
        ).json()["id"]
        controller = request(
            app,
            "POST",
            f"/api/v1/simulations/{simulation}/controller",
            headers=auth,
            json={"filename": "controller.py", "source": "def control(ctx): return {}"},
        )
    finally:
        app.state.resources.close()

    assert denied.status_code == 401
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert rejected_origin.status_code == 400
    assert "access-control-allow-origin" not in rejected_origin.headers
    assert created.status_code == 201
    assert controller.status_code == 403
    assert "disabled" in controller.json()["error"]




def test_websocket_replaces_qt_runtime_signals() -> None:
    application = WebApplication(Path.cwd())
    try:
        response = application.dispatch(
            "setEditorState",
            [json.dumps(Scene(name="WebSocket Scene").to_dict()), True, ""],
        )
        event = application.events_since(0)[0]
    finally:
        application.close()

    assert response["ok"] is True
    assert event["type"] == "title"
    assert event["payload"] == "*SimLab - WebSocket Scene"
