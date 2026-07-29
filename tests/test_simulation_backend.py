from __future__ import annotations

import json
from pathlib import Path

import pytest

from simlab.models.actor import Actor
from simlab.models.robotics import RoboticsModel
from simlab.models.scene import Scene
from simlab.simulation.backend import (
    BackendSessionClosedError,
    ControlCommand,
    InvalidControlError,
    ModelSchemaMismatchError,
    ResetOptions,
    SceneBundle,
)
from simlab.simulation.mujoco_backend import MujocoBackend
from simlab.simulation.robot_adapter import DirectActuatorAdapter


def _robot_scene() -> Scene:
    robotics = RoboticsModel.from_dict(
        json.loads(Path("tests/fixtures/robotics/two_joint_arm.json").read_text(encoding="utf-8"))
    )
    return Scene(
        name="Algorithm Backend Arm",
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id="two_joint_arm",
                properties={"articulation_ids": ["arm_demo"]},
            )
        ],
        robotics=robotics,
        simulation_config={"timestep": 0.01},
    )


def test_scene_bundle_is_immutable_and_detects_payload_changes() -> None:
    bundle = SceneBundle.from_scene(_robot_scene())

    assert bundle.scene().name == "Algorithm Backend Arm"
    tampered = SceneBundle(
        scene_json=bundle.scene_json.replace("Algorithm Backend Arm", "Changed"),
        scene_hash=bundle.scene_hash,
    )
    with pytest.raises(RuntimeError, match="content hash"):
        tampered.scene()


def test_mujoco_backend_exposes_engine_neutral_atomic_step(tmp_path) -> None:
    pytest.importorskip("mujoco")
    bundle = SceneBundle.from_scene(
        _robot_scene(),
        asset_root=tmp_path,
        export_path=tmp_path / "algorithm" / "scene.xml",
    )
    session = MujocoBackend().create_session(bundle)
    description = session.model_description

    assert description.backend_name == "mujoco-local"
    assert [item.id for item in description.joints] == [
        "joint_shoulder",
        "joint_elbow",
    ]
    assert [item.id for item in description.actuators] == [
        "actuator_shoulder",
        "actuator_elbow",
    ]
    assert [item.id for item in description.bodies] == [
        "actor_arm",
        "link_base",
        "link_upper_arm",
        "link_forearm",
    ]

    initial = session.reset(
        seed=7,
        options=ResetOptions(
            joint_positions={"joint_shoulder": 0.1},
            actuator_controls={"actuator_shoulder": 0.1},
        ),
    )
    stepped = session.step(
        ControlCommand(
            schema_hash=description.schema_hash,
            values=(0.8, -1.0),
        ),
        physics_steps=25,
    )

    assert initial.joint_positions == pytest.approx((0.1, -0.4))
    assert stepped.step_index == 25
    assert stepped.time == pytest.approx(0.25)
    assert stepped.actuator_controls == pytest.approx((0.8, -1.0))
    assert len(stepped.body_positions) == len(description.bodies)

    with pytest.raises(ModelSchemaMismatchError):
        session.step(ControlCommand(schema_hash="other", values=(0.0, 0.0)))
    with pytest.raises(InvalidControlError, match="actuator controls"):
        session.step(ControlCommand(schema_hash=description.schema_hash, values=(0.0,)))
    with pytest.raises(InvalidControlError, match="actuator_shoulder"):
        session.step(ControlCommand(schema_hash=description.schema_hash, values=(99.0, 0.0)))

    session.close()
    with pytest.raises(BackendSessionClosedError):
        session.reset()


def test_robot_adapter_uses_stable_ids_and_preserves_unowned_controls(tmp_path) -> None:
    pytest.importorskip("mujoco")
    session = MujocoBackend().create_session(
        SceneBundle.from_scene(_robot_scene(), export_path=tmp_path / "adapter" / "scene.xml")
    )
    state = session.reset()
    adapter = DirectActuatorAdapter(["actuator_shoulder"], joint_ids=["joint_shoulder"]).bind(
        session.model_description
    )

    command = adapter.command([1.0], state)

    assert command.values == pytest.approx((1.57, -0.4))
    assert adapter.observation(state).tolist() == pytest.approx([0.0, 0.0])
    with pytest.raises(InvalidControlError, match="shape"):
        adapter.command([0.0, 0.0], state)
    session.close()
