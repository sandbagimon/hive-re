from __future__ import annotations

import pytest

from simlab.models.robotics import RigidTransform, Sensor
from simlab.services.imu_sensors import ImuKinematics, ImuSensorScheduler


def _sensor(identifier: str, rate: float | None) -> Sensor:
    return Sensor(
        id=identifier,
        name=identifier,
        sensor_type="imu",
        link_id="link_forearm",
        update_rate_hz=rate,
        local_transform=RigidTransform(position=[0.0, 0.0, 0.25]),
    )


def _measurement(angular_velocity: float = 0.0) -> ImuKinematics:
    return ImuKinematics(
        orientation=(0.0, 0.0, 0.0, 1.0),
        angular_velocity=(0.0, angular_velocity, 0.0),
        linear_acceleration=(0.0, 0.0, 9.81),
    )


def test_imu_sensor_scheduler_samples_exact_step_divisors() -> None:
    scheduler = ImuSensorScheduler(
        [_sensor("imu_100hz", 100.0), _sensor("imu_50hz", 50.0)],
        timestep=0.01,
    )
    home = {"imu_100hz": _measurement(), "imu_50hz": _measurement()}
    moved = {"imu_100hz": _measurement(1.5), "imu_50hz": _measurement(1.5)}

    initial = scheduler.reset(0.0, home)
    first = scheduler.capture(1, 0.01, moved)
    second = scheduler.capture(2, 0.02, moved)

    assert [(sample.sensor_id, sample.sequence) for sample in initial] == [
        ("imu_100hz", 0),
        ("imu_50hz", 0),
    ]
    assert [sample.sensor_id for sample in first] == ["imu_100hz"]
    assert [sample.sensor_id for sample in second] == ["imu_100hz", "imu_50hz"]
    assert scheduler.latest_samples[1].to_dict() == {
        "id": "imu_50hz",
        "sensor_type": "imu",
        "link_id": "link_forearm",
        "time": 0.02,
        "sequence": 1,
        "orientation": [0.0, 0.0, 0.0, 1.0],
        "angular_velocity": [0.0, 1.5, 0.0],
        "linear_acceleration": [0.0, 0.0, 9.81],
    }


@pytest.mark.parametrize("rate", [60.0, 101.0])
def test_imu_scheduler_rejects_non_divisor_rate(rate: float) -> None:
    with pytest.raises(ValueError, match="exact divisor"):
        ImuSensorScheduler([_sensor("imu", rate)], timestep=0.01)


def test_imu_scheduler_requires_definition_and_measurement() -> None:
    missing_link = _sensor("imu_missing_link", 100.0)
    missing_link.link_id = None
    with pytest.raises(ValueError, match="requires link_id"):
        ImuSensorScheduler([missing_link], 0.01)

    missing_transform = _sensor("imu_missing_transform", 100.0)
    missing_transform.local_transform = None
    with pytest.raises(ValueError, match="requires local_transform"):
        ImuSensorScheduler([missing_transform], 0.01)

    scheduler = ImuSensorScheduler([_sensor("imu_missing_value", 100.0)], 0.01)
    with pytest.raises(ValueError, match="Missing IMU measurement"):
        scheduler.reset(0.0, {})


def test_imu_kinematics_requires_normalized_finite_orientation() -> None:
    with pytest.raises(ValueError, match="normalized"):
        ImuKinematics(
            orientation=(0.0, 0.0, 0.0, 2.0),
            angular_velocity=(0.0, 0.0, 0.0),
            linear_acceleration=(0.0, 0.0, 0.0),
        )
