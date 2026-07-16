import json
from pathlib import Path

import pytest

from simlab.models.actor import Actor
from simlab.models.robotics import RoboticsModel
from simlab.models.scene import Scene
from simlab.models.trajectory import (
    JointTrajectory,
    JointTrajectoryKeyframe,
    SceneTrajectory,
)
from simlab.services.project_service import (
    ProjectValidationError,
    load_scene,
    save_scene,
    validate_scene,
)


def _robotics() -> RoboticsModel:
    data = json.loads(
        Path("tests/fixtures/robotics/two_joint_arm.json").read_text(encoding="utf-8")
    )
    return RoboticsModel.from_dict(data)


def _trajectory(*, joint_id: str = "joint_shoulder") -> SceneTrajectory:
    return SceneTrajectory(
        id="trajectory_pick",
        actor_id="actor_001",
        trajectory=JointTrajectory(
            name="Pick",
            keyframes=[
                JointTrajectoryKeyframe(0, {joint_id: 0}),
                JointTrajectoryKeyframe(1, {joint_id: 0.5}),
            ],
        ),
    )


def _scene() -> Scene:
    return Scene(
        name="Robot Trajectory",
        actors=[
            Actor(
                id="actor_001",
                name="Arm",
                type="robot",
                asset_id="external_arm",
                properties={"articulation_ids": ["arm_demo"]},
            )
        ],
        robotics=_robotics(),
        trajectories=[_trajectory()],
    )


def test_scene_trajectory_library_saves_and_loads(tmp_path: Path) -> None:
    path = tmp_path / "scene.json"

    save_scene(path, _scene())
    restored = load_scene(path)

    assert restored.trajectories[0].id == "trajectory_pick"
    assert restored.trajectories[0].actor_id == "actor_001"
    assert restored.trajectories[0].trajectory.keyframes[-1].targets == {
        "joint_shoulder": 0.5
    }


def test_scene_trajectory_ids_must_be_unique() -> None:
    scene = _scene()
    scene.trajectories.append(_trajectory())

    with pytest.raises(ProjectValidationError, match="Trajectory ids must be unique"):
        validate_scene(scene)


def test_scene_trajectory_actor_must_exist() -> None:
    scene = _scene()
    scene.trajectories[0].actor_id = "actor_999"

    with pytest.raises(ProjectValidationError, match="references unknown actor"):
        validate_scene(scene)


def test_scene_trajectory_actor_must_be_robot() -> None:
    scene = _scene()
    scene.actors[0].type = "object"

    with pytest.raises(ProjectValidationError, match="must be a robot"):
        validate_scene(scene)


def test_scene_trajectory_targets_robot_position_joints() -> None:
    scene = _scene()
    scene.trajectories = [_trajectory(joint_id="joint_missing")]

    with pytest.raises(ProjectValidationError, match="unknown position joint"):
        validate_scene(scene)
