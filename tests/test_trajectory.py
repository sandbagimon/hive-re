from __future__ import annotations

import pytest

from simlab.models.trajectory import JointTrajectory
from simlab.services.trajectory_player import JointTrajectoryPlayer
from simlab.services.trajectory_validation import (
    TrajectoryValidationError,
    validate_joint_trajectory,
)


def _trajectory(*, loop: bool = False) -> JointTrajectory:
    return JointTrajectory.from_dict(
        {
            "version": "1.0",
            "name": "Reach",
            "loop": loop,
            "keyframes": [
                {"time": 0.0, "targets": {"shoulder": 0.0, "elbow": -0.4}},
                {"time": 1.0, "targets": {"shoulder": 1.0, "elbow": -1.0}},
                {"time": 2.0, "targets": {"shoulder": 0.5, "elbow": -0.2}},
            ],
        }
    )


def test_joint_trajectory_round_trip_and_validation() -> None:
    trajectory = _trajectory()

    validate_joint_trajectory(
        trajectory,
        allowed_joint_ids={"shoulder", "elbow", "wrist"},
    )

    assert JointTrajectory.from_dict(trajectory.to_dict()).to_dict() == trajectory.to_dict()
    assert trajectory.duration == 2.0
    assert trajectory.joint_ids == {"shoulder", "elbow"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(keyframes=data["keyframes"][:1]), "at least two"),
        (lambda data: data["keyframes"][0].update(time=0.1), "must start at time 0"),
        (lambda data: data["keyframes"][1].update(time=0.0), "strictly increasing"),
        (
            lambda data: data["keyframes"][1]["targets"].pop("elbow"),
            "same joint IDs",
        ),
        (
            lambda data: data["keyframes"][1]["targets"].update(shoulder=float("nan")),
            "must be finite",
        ),
    ],
)
def test_joint_trajectory_rejects_invalid_keyframes(mutation, message: str) -> None:
    data = _trajectory().to_dict()
    mutation(data)
    trajectory = JointTrajectory.from_dict(data)

    with pytest.raises(TrajectoryValidationError, match=message):
        validate_joint_trajectory(trajectory)


def test_joint_trajectory_rejects_unknown_position_joint() -> None:
    with pytest.raises(TrajectoryValidationError, match="unknown position joint"):
        validate_joint_trajectory(
            _trajectory(),
            allowed_joint_ids={"shoulder"},
        )


def test_trajectory_player_interpolates_pause_resume_and_complete() -> None:
    player = JointTrajectoryPlayer()
    player.load(_trajectory())
    player.play(10.0)

    assert player.sample(10.5) == pytest.approx({"shoulder": 0.5, "elbow": -0.7})
    paused = player.pause(10.5)
    assert paused.status == "paused"
    assert player.sample(20.0) == pytest.approx({"shoulder": 0.5, "elbow": -0.7})

    player.play(20.0)
    assert player.sample(21.5) == pytest.approx({"shoulder": 0.5, "elbow": -0.2})
    assert player.state().status == "completed"
    stopped = player.stop()
    assert stopped.status == "stopped"
    assert player.sample(99.0) == pytest.approx({"shoulder": 0.0, "elbow": -0.4})


def test_trajectory_player_loops_by_simulation_time() -> None:
    player = JointTrajectoryPlayer()
    player.load(_trajectory(loop=True))
    player.play(5.0)

    assert player.sample(7.5) == pytest.approx({"shoulder": 0.5, "elbow": -0.7})
    assert player.state().status == "playing"
