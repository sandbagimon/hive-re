import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
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
