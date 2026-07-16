import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.trajectory import JointTrajectory
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


def test_robot_session_plays_pauses_and_stops_joint_trajectory(tmp_path) -> None:
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
    trajectory = JointTrajectory.from_dict(
        {
            "version": "1.0",
            "name": "Reach",
            "loop": False,
            "keyframes": [
                {
                    "time": 0,
                    "targets": {
                        shoulder.id: shoulder.initial_position,
                        elbow.id: elbow.initial_position,
                    },
                },
                {"time": 0.5, "targets": {shoulder.id: 0.6, elbow.id: -1.0}},
            ],
        }
    )

    loaded = session.load_joint_trajectory(trajectory)
    playing = session.play_trajectory()
    completed = session.step(steps=50)

    assert loaded.trajectory.status == "stopped"
    assert playing.trajectory.status == "playing"
    assert completed.trajectory.status == "completed"
    assert completed.trajectory.time == pytest.approx(0.5)
    assert [state.ctrl for state in completed.actuators] == pytest.approx([0.6, -1.0])
    assert completed.joints[0].qpos > 0.1

    session.load_joint_trajectory(trajectory)
    session.play_trajectory()
    session.step(steps=20)
    paused = session.pause_trajectory()
    paused_ctrl = [state.ctrl for state in paused.actuators]
    stepped_while_paused = session.step(steps=10)
    assert stepped_while_paused.trajectory.time == pytest.approx(paused.trajectory.time)
    assert [state.ctrl for state in stepped_while_paused.actuators] == pytest.approx(
        paused_ctrl
    )

    stopped = session.stop_trajectory()
    assert stopped.trajectory.status == "stopped"
    assert [state.ctrl for state in stopped.actuators] == pytest.approx(
        [shoulder.initial_position, elbow.initial_position]
    )


def test_robot_session_rejects_trajectory_for_unknown_joint(tmp_path) -> None:
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
    trajectory = JointTrajectory.from_dict(
        {
            "version": "1.0",
            "name": "Invalid",
            "loop": False,
            "keyframes": [
                {"time": 0, "targets": {"joint_missing": 0}},
                {"time": 1, "targets": {"joint_missing": 1}},
            ],
        }
    )

    with pytest.raises(ValueError, match="unknown position joint"):
        session.load_joint_trajectory(trajectory)


def test_robot_session_records_every_physics_step(tmp_path) -> None:
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
    articulation = imported.robotics_model.articulations[0]
    shoulder = articulation.joints[0]
    shoulder_drive = articulation.actuators[0]

    started = session.start_joint_recording(
        name="Shoulder Run",
        joint_ids=[shoulder.id],
        actuator_ids=[shoulder_drive.id],
    )
    stepped = session.step(steps=4)
    stopped, recording = session.stop_joint_recording()

    assert started.recording.active is True
    assert started.recording.sample_count == 1
    assert stepped.recording.sample_count == 5
    assert stopped.recording.active is False
    assert [sample.time for sample in recording.samples] == pytest.approx(
        [0.0, 0.01, 0.02, 0.03, 0.04]
    )
    assert all(set(sample.joints) == {shoulder.id} for sample in recording.samples)
    assert all(
        set(sample.actuators) == {shoulder_drive.id} for sample in recording.samples
    )


def test_robot_session_recording_limit_stops_capture(tmp_path) -> None:
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
        simulation_config={
            "timestep": 0.01,
            "duration": 1.0,
            "recording_max_samples": 3,
        },
    )
    session = MuJoCoSimulationSession(scene, tmp_path / "scene.xml", asset_root=tmp_path)

    session.start_joint_recording(name="Bounded")
    limited = session.step(steps=4)

    assert limited.recording.active is False
    assert limited.recording.limit_reached is True
    assert limited.recording.sample_count == 3
    assert session.joint_recording is not None
    assert len(session.joint_recording.samples) == 3
