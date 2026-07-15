import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.openusd_importer import import_openusd_asset
from simlab.services.simulation_session import (
    MuJoCoSimulationSession,
    SimulationRuntimeError,
)


def test_mujoco_simulation_session_returns_actor_pose_state(tmp_path) -> None:
    pytest.importorskip("mujoco")
    scene = Scene(name="Live Sync Test")
    scene.actors.append(
        Actor(
            id="actor_001",
            name="Box",
            type="object",
            asset_id="primitive_box",
            transform=Transform(position=[0, 0, 1]),
            properties={"primitive": "box", "size": [0.2, 0.2, 0.2], "mass": 1.0},
        )
    )

    session = MuJoCoSimulationSession(scene, tmp_path / "scene.xml")
    initial = session.state()
    stepped = session.step()

    assert initial.actors[0].actor_id == "actor_001"
    assert initial.actors[0].position == [0.0, 0.0, 1.0]
    assert len(initial.actors[0].quaternion) == 4
    assert stepped.time > initial.time
    assert stepped.to_dict()["actors"][0]["id"] == "actor_001"


def test_robot_session_publishes_home_link_joint_and_actuator_state(tmp_path) -> None:
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
    session = MuJoCoSimulationSession(
        scene, tmp_path / "exports" / "scene.xml", asset_root=tmp_path
    )

    initial = session.state()
    stepped = session.step(steps=2)
    reset = session.reset()

    assert len(initial.links) == 3
    assert len(initial.joints) == 2
    assert len(initial.actuators) == 2
    assert initial.joints[1].qpos == pytest.approx(-0.4)
    assert stepped.time > 0
    assert reset.time == 0
    assert reset.joints[1].qpos == pytest.approx(-0.4)
    payload = reset.to_dict()
    assert {item["id"] for item in payload["links"]} == {
        link.id for link in imported.robotics_model.articulations[0].links
    }


def test_robot_session_clamps_joint_targets_and_reset_restores_home(tmp_path) -> None:
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
    session = MuJoCoSimulationSession(scene, tmp_path / "scene.xml", asset_root=tmp_path)
    shoulder, elbow = imported.robotics_model.articulations[0].joints

    commanded = session.set_joint_position_targets(
        {shoulder.id: 99.0, elbow.id: -1.0}
    )
    stepped = session.step(steps=20)

    assert commanded.actuators[0].ctrl == pytest.approx(1.57079632679)
    assert commanded.actuators[1].ctrl == pytest.approx(-1.0)
    assert stepped.joints[0].qpos > 0
    reset = session.reset()
    assert reset.joints[1].qpos == pytest.approx(-0.4)
    assert reset.actuators[1].ctrl == pytest.approx(-0.4)
    with pytest.raises(ValueError, match="No position actuator"):
        session.set_joint_position_targets({"joint_missing": 0.0})


def test_robot_joint_commands_are_atomic_and_publish_fault_state(tmp_path) -> None:
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
    session = MuJoCoSimulationSession(scene, tmp_path / "scene.xml", asset_root=tmp_path)
    shoulder = imported.robotics_model.articulations[0].joints[0]
    before = [state.ctrl for state in session.state().actuators]

    with pytest.raises(ValueError, match="joint_missing"):
        session.set_joint_position_targets({shoulder.id: 0.5, "joint_missing": 0.0})

    fault = session.state()
    assert [state.ctrl for state in fault.actuators] == before
    assert fault.controller.status == "fault"
    assert "joint_missing" in (fault.controller.message or "")


def test_robot_control_watchdog_returns_targets_home(tmp_path) -> None:
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
        simulation_config={"timestep": 0.01, "control_timeout": 0.05},
    )
    session = MuJoCoSimulationSession(scene, tmp_path / "scene.xml", asset_root=tmp_path)
    shoulder, elbow = imported.robotics_model.articulations[0].joints

    active = session.set_joint_position_targets({shoulder.id: 0.5, elbow.id: -1.0})
    timed_out = session.step(steps=10)

    assert active.controller.status == "active"
    assert active.controller.timeout == pytest.approx(0.05)
    assert timed_out.controller.status == "timed_out"
    assert [state.ctrl for state in timed_out.actuators] == pytest.approx(
        [shoulder.initial_position, elbow.initial_position]
    )


def test_robot_session_rejects_non_finite_runtime_state_with_context(tmp_path) -> None:
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
    session = MuJoCoSimulationSession(scene, tmp_path / "scene.xml", asset_root=tmp_path)
    joint_id = imported.robotics_model.articulations[0].joints[0].id
    session.data.qpos[0] = float("nan")

    with pytest.raises(SimulationRuntimeError, match=rf"joint {joint_id} qpos"):
        session.state()

    assert session._controller_status == "fault"
