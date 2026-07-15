import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

from simlab.editor_bridge import EditorBridge
from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.openusd_importer import import_openusd_asset
from simlab.services.project_service import load_scene


def _bridge(project_root: Path | None = None) -> EditorBridge:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    parent = QWidget()
    return EditorBridge(parent, project_root or Path.cwd())


def test_editor_bridge_returns_enriched_assets() -> None:
    bridge = _bridge()

    response = json.loads(bridge.getAssets())

    assert response["ok"] is True
    sphere = next(
        asset for asset in response["data"]["assets"] if asset["id"] == "primitive_sphere"
    )
    physics = sphere["default_properties"]["physics"]
    assert physics["material"] == "rubber"
    assert len(physics["solimp"]) == 5


def test_editor_bridge_preflight_uses_scene_snapshot() -> None:
    bridge = _bridge()
    scene = load_scene("examples/demo_project/scene.json")

    response = json.loads(bridge.preflight(json.dumps(scene.to_dict())))

    assert response["ok"] is True
    assert response["data"]["valid"] is True
    assert response["data"]["issues"] == []


def test_editor_bridge_imports_openusd_and_serves_visual_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("pxr")
    source = Path("tests/fixtures/openusd/tetrahedron.usda").resolve()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    bridge = _bridge(tmp_path)

    response = json.loads(bridge.importOpenUsd())

    assert response["ok"] is True
    asset = response["data"]["asset"]
    assert asset["source_format"] == "openusd"
    cache_path = asset["default_properties"]["geometry"]["visual_cache"]
    geometry_response = json.loads(bridge.getVisualGeometry(cache_path))
    assert geometry_response["ok"] is True
    assert len(geometry_response["data"]["positions"]) == 12


def test_editor_bridge_imports_external_usd_robot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("pxr")
    source = Path(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda"
    ).resolve()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    bridge = _bridge(tmp_path)

    response = json.loads(bridge.importOpenUsd())

    assert response["ok"] is True
    assert response["data"]["asset"]["type"] == "robot"
    assert len(response["data"]["robotics"]["articulations"][0]["joints"]) == 2


def test_editor_bridge_external_robot_rpc_workflow(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    source = Path(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda"
    ).resolve()
    bridge = _bridge(tmp_path)
    wall_time = [100.0]
    bridge.simulation_service.clock = lambda: wall_time[0]
    statuses: list[str] = []
    states: list[dict] = []
    bridge.simulationStatusChanged.connect(statuses.append)
    bridge.simulationStateChanged.connect(lambda value: states.append(json.loads(value)))

    imported = json.loads(bridge.importOpenUsdPath(str(source)))
    assert imported["ok"] is True
    asset = imported["data"]["asset"]
    scene = Scene.from_dict(
        {
            "version": "1.0",
            "name": "Bridge Robot Workflow",
            "units": "meters",
            "actors": [
                {
                    "id": "actor_external_arm",
                    "name": "External Arm",
                    "type": "robot",
                    "asset_id": asset["id"],
                    "properties": asset["default_properties"],
                }
            ],
            "robotics": imported["data"]["robotics"],
            "simulation_config": {"timestep": 0.01, "max_catch_up_steps": 4},
        }
    )
    articulation = scene.robotics.articulations[0]
    shoulder, elbow = articulation.joints

    started = json.loads(bridge.runSimulation(json.dumps(scene.to_dict())))
    commanded = json.loads(
        bridge.setJointTargets(
            json.dumps(scene.to_dict()),
            json.dumps({shoulder.id: 0.6, elbow.id: -1.0}),
        )
    )
    for _ in range(40):
        wall_time[0] += 0.02
        bridge._advance_simulation()
    paused = json.loads(bridge.pauseSimulation())
    reset = json.loads(bridge.resetSimulation())

    assert started["ok"] is True
    assert commanded["data"]["state"]["controller"]["status"] == "active"
    assert paused["ok"] is True
    assert states[-2]["time"] == pytest.approx(0.8)
    assert abs(states[-2]["joints"][0]["qpos"]) > 0.1
    assert reset["data"]["state"]["time"] == 0.0
    assert reset["data"]["state"]["joints"][0]["qpos"] == pytest.approx(
        shoulder.initial_position
    )
    assert statuses[0] == "running"
    assert statuses[-2:] == ["paused", "paused"]


def test_editor_bridge_sets_robot_joint_target(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    assert imported.robotics_model is not None
    scene = Scene(
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
    )
    joint_id = imported.robotics_model.articulations[0].joints[0].id
    bridge = _bridge(tmp_path)

    response = json.loads(
        bridge.setJointTargets(json.dumps(scene.to_dict()), json.dumps({joint_id: 0.5}))
    )

    assert response["ok"] is True
    assert response["data"]["state"]["actuators"][0]["ctrl"] == pytest.approx(0.5)


def test_editor_bridge_returns_controller_fault_state(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    scene = Scene(
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
    )
    bridge = _bridge(tmp_path)

    response = json.loads(
        bridge.setJointTargets(
            json.dumps(scene.to_dict()), json.dumps({"joint_missing": 0.5})
        )
    )

    assert response["ok"] is False
    assert response["data"]["state"]["controller"]["status"] == "fault"


def test_editor_bridge_contains_runtime_fault_from_timer(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    statuses: list[str] = []
    messages: list[str] = []
    bridge.simulationStatusChanged.connect(statuses.append)
    bridge.consoleMessage.connect(messages.append)

    def fail_frame():
        raise RuntimeError("non-finite joint state")

    bridge.simulation_service.step_frame = fail_frame
    bridge.simulation_timer.start()

    bridge._advance_simulation()

    assert bridge.simulation_timer.isActive() is False
    assert statuses == ["fault"]
    assert messages == ["Simulation fault: non-finite joint state"]


def test_editor_bridge_reset_publishes_robot_home_state(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    scene = Scene(
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
    )
    shoulder = imported.robotics_model.articulations[0].joints[0]
    bridge = _bridge(tmp_path)
    statuses: list[str] = []
    states: list[dict] = []
    bridge.simulationStatusChanged.connect(statuses.append)
    bridge.simulationStateChanged.connect(lambda value: states.append(json.loads(value)))
    bridge.setJointTargets(json.dumps(scene.to_dict()), json.dumps({shoulder.id: 0.5}))

    response = json.loads(bridge.resetSimulation())

    assert response["ok"] is True
    assert response["data"]["state"]["time"] == 0.0
    assert response["data"]["state"]["controller"]["status"] == "ready"
    assert response["data"]["state"]["joints"][0]["qpos"] == shoulder.initial_position
    assert bridge.simulation_service.session is not None
    assert statuses == ["paused"]
    assert states[-1] == response["data"]["state"]
