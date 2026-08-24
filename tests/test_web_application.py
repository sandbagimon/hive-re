import asyncio
import base64
import io
import json
from pathlib import Path

import httpx
import pytest

from beefoundrysim.models.actor import Actor
from beefoundrysim.models.attachment import Attachment
from beefoundrysim.models.robotics import RoboticsModel, Sensor
from beefoundrysim.models.scene import Scene
from beefoundrysim.models.transform import Transform
from beefoundrysim.resources import ResourceManager
from beefoundrysim.services.project_service import load_scene
from beefoundrysim.web_application import WebApplication
from beefoundrysim.web_server import create_app


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


def test_api_imports_multipart_openusd_directory_with_relative_dependencies(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/openusd/composite")
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    try:
        project_id = create_api_project(app)
        response = request(
            app,
            "POST",
            f"/api/v1/projects/{project_id}/assets/openusd",
            data={"entry": "composite/root.usda"},
            files=[
                (
                    "files",
                    (
                        "composite/root.usda",
                        io.BytesIO((fixture / "root.usda").read_bytes()),
                        "application/octet-stream",
                    ),
                ),
                (
                    "files",
                    (
                        "composite/parts/geometry.usda",
                        io.BytesIO((fixture / "parts" / "geometry.usda").read_bytes()),
                        "application/octet-stream",
                    ),
                ),
            ],
        )
    finally:
        app.state.resources.close()

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["asset"]["name"] == "root"
    assert payload["asset"]["type"] == "object"
    assert payload["asset"]["default_properties"]["geometry"]["visual_cache"].startswith(
        "art_"
    )
    upload_root = tmp_path / "projects" / project_id / "assets" / "uploads"
    assert not upload_root.exists() or not any(upload_root.iterdir())


def test_api_serves_imported_openusd_texture_as_authenticated_artifact(
    tmp_path: Path,
) -> None:
    source = b'''#usda 1.0
(defaultPrim = "Asset")
def Xform "Asset"
{
    def Mesh "Triangle"
    {
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        texCoord2f[] primvars:st = [(0, 0), (1, 0), (0, 1)] (
            interpolation = "vertex"
        )
        rel material:binding = </Looks/Textured>
    }
}
def Scope "Looks"
{
    def Material "Textured"
    {
        token outputs:surface.connect = </Looks/Textured/Preview.outputs:surface>
        def Shader "Preview"
        {
            uniform token info:id = "UsdPreviewSurface"
            color3f inputs:diffuseColor.connect = </Looks/Textured/Texture.outputs:rgb>
            normal3f inputs:normal.connect = </Looks/Textured/Normal.outputs:rgb>
            float inputs:roughness.connect = </Looks/Textured/Roughness.outputs:r>
            float inputs:metallic.connect = </Looks/Textured/Metallic.outputs:r>
            token outputs:surface
        }
        def Shader "Texture"
        {
            uniform token info:id = "UsdUVTexture"
            asset inputs:file = @albedo.png@
            float3 outputs:rgb
        }
        def Shader "Normal"
        {
            uniform token info:id = "UsdUVTexture"
            asset inputs:file = @normal.png@
            float3 outputs:rgb
        }
        def Shader "Roughness"
        {
            uniform token info:id = "UsdUVTexture"
            asset inputs:file = @roughness.png@
            float outputs:r
        }
        def Shader "Metallic"
        {
            uniform token info:id = "UsdUVTexture"
            asset inputs:file = @metallic.png@
            float outputs:r
        }
    }
}
'''
    textures = {
        "base_color_texture": ("albedo.png", b"beefoundrysim-base-color"),
        "normal_texture": ("normal.png", b"beefoundrysim-normal"),
        "roughness_texture": ("roughness.png", b"beefoundrysim-roughness"),
        "metallic_texture": ("metallic.png", b"beefoundrysim-metallic"),
    }
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    try:
        project_id = create_api_project(app)
        imported = request(
            app,
            "POST",
            f"/api/v1/projects/{project_id}/assets/openusd",
            data={"entry": "textured.usda"},
            files=[("files", ("textured.usda", source, "application/octet-stream"))]
            + [
                ("files", (filename, content, "image/png"))
                for filename, content in textures.values()
            ],
        )
        visual_artifact = imported.json()["asset"]["default_properties"]["geometry"][
            "visual_cache"
        ]
        geometry = request(
            app,
            "GET",
            f"/api/v1/projects/{project_id}/geometry/{visual_artifact}",
        )
        texture_artifacts = {
            field: geometry.json()[field]
            for field in textures
        }
        downloaded = {
            field: request(app, "GET", f"/api/v1/artifacts/{artifact}")
            for field, artifact in texture_artifacts.items()
        }
    finally:
        app.state.resources.close()

    assert imported.status_code == 201, imported.text
    assert geometry.status_code == 200, geometry.text
    assert geometry.json()["uvs"] == pytest.approx([0, 0, 1, 0, 0, 1])
    for field, artifact in texture_artifacts.items():
        assert artifact.startswith("art_")
        assert downloaded[field].headers["content-type"] == "image/png"
        assert downloaded[field].content == textures[field][1]


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
        openapi = request(app, "GET", "/api/v1/openapi.json")
        frontend = request(app, "GET", "/")
        legacy_rpc = request(app, "POST", "/api/rpc/getAssets", json={"args": []})
        project_id = create_api_project(app)
        assets = request(app, "GET", f"/api/v1/projects/{project_id}/assets")
    finally:
        app.state.resources.close()

    assert health.status_code == 200
    assert health.json() == {"version": "v1", "status": "ok"}
    upload_content = openapi.json()["paths"][
        "/api/v1/projects/{project_id}/assets/openusd"
    ]["post"]["requestBody"]["content"]
    assert set(upload_content) == {"multipart/form-data", "application/json"}
    assert all(path.startswith("/api/") for path in route_paths)
    assert "/redoc" not in route_paths
    assert frontend.status_code == 404
    assert legacy_rpc.status_code == 404
    assert assets.status_code == 200
    assert assets.json()["version"] == "v1"
    assert assets.json()["assets"]
    robot = next(asset for asset in assets.json()["assets"] if asset["type"] == "robot")
    assert robot["name"] == "Two-Joint Robot Arm"
    assert len(robot["robotics"]["articulations"][0]["links"]) == 3
    assert len(robot["robotics"]["articulations"][0]["joints"]) == 2


def test_api_streams_immutable_geometry_bundle_with_conditional_cache(
    tmp_path: Path,
) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "metadata.json").write_text('{"assets": []}\n', encoding="utf-8")
    app = create_app(tmp_path / "data", seed_assets=seed)
    try:
        project_id = create_api_project(app)
        project = app.state.resources.get_project(project_id)
        bundle_path = project.root / "assets" / "visual-test.simbin"
        bundle_path.write_bytes(b"SIMGEOM1-test-bundle")
        external = app.state.resources.externalize(
            project,
            {"visual_bundle": "assets/visual-test.simbin"},
        )
        artifact_id = external["visual_bundle"]
        downloaded = request(app, "GET", f"/api/v1/artifacts/{artifact_id}")
        unchanged = request(
            app,
            "GET",
            f"/api/v1/artifacts/{artifact_id}",
            headers={"If-None-Match": downloaded.headers["etag"]},
        )
    finally:
        app.state.resources.close()

    assert downloaded.status_code == 200
    assert downloaded.content == b"SIMGEOM1-test-bundle"
    assert downloaded.headers["cache-control"].endswith("immutable")
    assert downloaded.headers["content-disposition"].startswith("inline;")
    assert unchanged.status_code == 304
    assert unchanged.content == b""


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


def test_api_applies_named_quadrotor_actuator_controls(tmp_path: Path) -> None:
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    try:
        project_id = create_api_project(app, "Iris API")
        assets = request(app, "GET", f"/api/v1/projects/{project_id}/assets").json()[
            "assets"
        ]
        iris = next(item for item in assets if item["id"] == "openusd_iris_09f8390b45")
        scene = Scene(
            name="Iris API Scene",
            actors=[
                Actor(
                    id="actor_001",
                    name="Iris",
                    type="robot",
                    asset_id=iris["id"],
                    transform=Transform(position=[0.0, 0.0, 1.0]),
                    properties=iris["default_properties"],
                )
            ],
            robotics=RoboticsModel.from_dict(iris["robotics"]),
            simulation_config={"timestep": 0.002, "duration": 1.0},
        )
        updated = request(
            app,
            "PUT",
            f"/api/v1/projects/{project_id}/scene",
            json=scene.to_dict(),
        )
        simulation_id = request(
            app,
            "POST",
            "/api/v1/simulations",
            json={"project_id": project_id},
        ).json()["id"]
        controls = {
            f"actuator_iris_rotor_{index}": 700.0 for index in range(4)
        }
        commanded = request(
            app,
            "PUT",
            f"/api/v1/simulations/{simulation_id}/actuator-controls",
            json={"controls": controls},
        )
        stepped = request(
            app,
            "POST",
            f"/api/v1/simulations/{simulation_id}/step",
        )
    finally:
        app.state.resources.close()

    assert updated.status_code == 200, updated.text
    assert commanded.status_code == 200, commanded.text
    assert [
        item["ctrl"] for item in commanded.json()["data"]["state"]["actuators"]
    ] == pytest.approx([700.0] * 4)
    assert stepped.status_code == 200, stepped.text
    assert stepped.json()["data"]["state"]["time"] == pytest.approx(0.002)


def test_api_activates_and_releases_contact_gated_attachment(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")

    def box(
        actor_id: str,
        position: list[float],
        size: list[float],
        *,
        dynamic: bool,
    ) -> Actor:
        return Actor(
            id=actor_id,
            name=actor_id,
            type="object",
            asset_id="primitive_box",
            transform=Transform(position=position),
            properties={
                "primitive": "box",
                "size": size,
                "physics": {
                    "dynamic": dynamic,
                    "mass_mode": "mass",
                    "mass": 1.0,
                },
            },
        )

    scene = Scene(
        name="Attachment API",
        actors=[
            box("carrier", [0.0, 0.0, 0.39], [0.1, 0.1, 0.1], dynamic=True),
            box("payload", [0.0, 0.0, 0.2], [0.15, 0.15, 0.1], dynamic=True),
            box("ground", [0.0, 0.0, -0.05], [2.0, 2.0, 0.05], dynamic=False),
        ],
        attachments=[
            Attachment(
                id="payload_hook",
                parent_body_id="carrier",
                child_body_id="payload",
                parent_anchor=(0.0, 0.0, -0.1),
                child_anchor=(0.0, 0.0, 0.1),
                capture_distance=0.03,
                capture_speed=0.2,
                capture_duration=0.0,
                require_contact=True,
            )
        ],
        simulation_config={"timestep": 0.002, "duration": 1.0},
    )
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    try:
        project_id = create_api_project(app, "Attachment API")
        updated = request(
            app,
            "PUT",
            f"/api/v1/projects/{project_id}/scene",
            json=scene.to_dict(),
        )
        simulation_id = request(
            app,
            "POST",
            "/api/v1/simulations",
            json={"project_id": project_id},
        ).json()["id"]
        attached = request(
            app,
            "PUT",
            f"/api/v1/simulations/{simulation_id}/attachments",
            json={"commands": {"payload_hook": True}},
        )
        released = request(
            app,
            "PUT",
            f"/api/v1/simulations/{simulation_id}/attachments",
            json={"commands": {"payload_hook": False}},
        )
    finally:
        app.state.resources.close()

    assert updated.status_code == 200, updated.text
    assert attached.status_code == 200, attached.text
    assert attached.json()["data"]["state"]["attachments"][0]["active"] is True
    assert released.status_code == 200, released.text
    assert released.json()["data"]["state"]["attachments"][0]["active"] is False


def test_catalog_robot_scene_rebinds_resources_when_opened_in_new_project(
    tmp_path: Path,
) -> None:
    manager = ResourceManager(tmp_path, Path.cwd() / "assets")
    try:
        first = manager.create_project("Iris Source")
        iris = next(
            item
            for item in manager.assets(first.id)
            if item["id"] == "openusd_iris_09f8390b45"
        )
        scene = Scene(
            name="Portable Iris",
            actors=[
                Actor(
                    id="actor_iris",
                    name="Iris",
                    type="robot",
                    asset_id=iris["id"],
                    transform=Transform(position=[0.0, 0.0, 1.0]),
                    properties=iris["default_properties"],
                )
            ],
            robotics=RoboticsModel.from_dict(iris["robotics"]),
        )
        saved = manager.update_scene(first.id, scene.to_dict()).scene
        old_collision = saved["robotics"]["articulations"][0]["links"][0][
            "colliders"
        ][0]["collision_mesh"]

        second = manager.create_project("Iris Destination")
        reopened = manager.update_scene(second.id, saved)
        new_collision = reopened.scene["robotics"]["articulations"][0]["links"][0][
            "colliders"
        ][0]["collision_mesh"]
        exported, _ = manager.export_mjcf(second.id)
    finally:
        manager.close()

    assert old_collision.startswith("art_")
    assert new_collision.startswith("art_")
    assert new_collision != old_collision
    assert "<mujoco" in exported["content"]


def test_project_edits_do_not_mutate_or_stop_simulation_snapshot(tmp_path: Path) -> None:
    scene = load_scene("examples/demo_project/scene.json")
    scene.name = "Simulation Snapshot"
    app = create_app(tmp_path, seed_assets=Path.cwd() / "assets")
    try:
        project_id = create_api_project(app)
        request(
            app,
            "PUT",
            f"/api/v1/projects/{project_id}/scene",
            json=scene.to_dict(),
        )
        simulation_id = request(
            app,
            "POST",
            "/api/v1/simulations",
            json={"project_id": project_id},
        ).json()["id"]
        run = request(app, "POST", f"/api/v1/simulations/{simulation_id}/run")
        assert run.json()["ok"] is True

        edited = scene.to_dict()
        edited["name"] = "Edited While Running"
        edited["actors"][0]["transform"]["position"][0] = 4.0
        updated = request(
            app,
            "PUT",
            f"/api/v1/projects/{project_id}/scene",
            json=edited,
        )
        original_snapshot = json.loads(
            app.state.resources.simulation_scene_json(simulation_id)
        )
        runtime = request(
            app, "GET", f"/api/v1/simulations/{simulation_id}/snapshot"
        ).json()
        next_simulation_id = request(
            app,
            "POST",
            "/api/v1/simulations",
            json={"project_id": project_id},
        ).json()["id"]
        next_snapshot = json.loads(
            app.state.resources.simulation_scene_json(next_simulation_id)
        )
    finally:
        app.state.resources.close()

    assert updated.status_code == 200
    assert runtime["status"] == "running"
    assert original_snapshot["name"] == "Simulation Snapshot"
    assert original_snapshot["actors"][0]["transform"]["position"][0] == 0.0
    assert next_snapshot["name"] == "Edited While Running"
    assert next_snapshot["actors"][0]["transform"]["position"][0] == 4.0


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
    assert downloaded.headers["x-beefoundrysim-artifact-id"] == artifact["id"]
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
    assert event["payload"] == "*BeeFoundrySim - WebSocket Scene"
