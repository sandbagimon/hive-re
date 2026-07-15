import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.openusd_importer import import_openusd_asset
from simlab.services.simulation_session import MuJoCoSimulationSession


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
