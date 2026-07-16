from __future__ import annotations

import pytest

from simlab.models.robotics import Sensor
from simlab.services.joint_state_sensors import (
    JointKinematics,
    JointStateSensorScheduler,
)


def _sensor(identifier: str, rate: float | None) -> Sensor:
    return Sensor(
        id=identifier,
        name=identifier,
        sensor_type="joint_state",
        joint_id="shoulder",
        update_rate_hz=rate,
    )


def test_joint_state_sensor_scheduler_samples_exact_step_divisors() -> None:
    scheduler = JointStateSensorScheduler(
        [_sensor("sensor_100hz", 100.0), _sensor("sensor_50hz", 50.0)],
        timestep=0.01,
    )
    home = {"shoulder": JointKinematics(qpos=0.0, qvel=0.0)}
    moved = {"shoulder": JointKinematics(qpos=0.2, qvel=1.5)}

    initial = scheduler.reset(0.0, home)
    first = scheduler.capture(1, 0.01, moved)
    second = scheduler.capture(2, 0.02, moved)

    assert [(item.sensor_id, item.sequence) for item in initial] == [
        ("sensor_100hz", 0),
        ("sensor_50hz", 0),
    ]
    assert [(item.sensor_id, item.sequence) for item in first] == [
        ("sensor_100hz", 1)
    ]
    assert [(item.sensor_id, item.sequence) for item in second] == [
        ("sensor_100hz", 2),
        ("sensor_50hz", 1),
    ]
    assert [item.to_dict() for item in scheduler.latest_samples] == [
        {
            "id": "sensor_100hz",
            "joint_id": "shoulder",
            "time": 0.02,
            "sequence": 2,
            "qpos": 0.2,
            "qvel": 1.5,
        },
        {
            "id": "sensor_50hz",
            "joint_id": "shoulder",
            "time": 0.02,
            "sequence": 1,
            "qpos": 0.2,
            "qvel": 1.5,
        },
    ]


@pytest.mark.parametrize("rate", [60.0, 101.0])
def test_joint_state_sensor_scheduler_rejects_non_divisor_rate(rate: float) -> None:
    with pytest.raises(ValueError, match="exact divisor"):
        JointStateSensorScheduler([_sensor("sensor", rate)], timestep=0.01)


def test_joint_state_sensor_scheduler_rejects_missing_or_unknown_joint() -> None:
    missing = _sensor("sensor_missing", 100.0)
    missing.joint_id = None
    with pytest.raises(ValueError, match="requires joint_id"):
        JointStateSensorScheduler([missing], timestep=0.01)

    scheduler = JointStateSensorScheduler([_sensor("sensor_unknown", None)], 0.01)
    with pytest.raises(ValueError, match="unknown joint"):
        scheduler.reset(0.0, {})
