from __future__ import annotations

import pytest

from simlab.models.robotics import Sensor
from simlab.services.contact_sensors import (
    ContactMeasurement,
    ContactSensorScheduler,
)


def _sensor(identifier: str, rate: float | None) -> Sensor:
    return Sensor(
        id=identifier,
        name=identifier,
        sensor_type="contact",
        collider_id="collider_finger",
        aggregation_mode="sum",
        update_rate_hz=rate,
    )


def _empty() -> ContactMeasurement:
    return ContactMeasurement(
        contact_count=0,
        normal_force=0.0,
        tangent_force=(0.0, 0.0, 0.0),
        normal_impulse=0.0,
    )


def _contact() -> ContactMeasurement:
    return ContactMeasurement(
        contact_count=1,
        normal_force=12.0,
        tangent_force=(1.0, -0.5, 0.0),
        normal_impulse=0.12,
        points=((0.1, 0.2, 0.3),),
        normals=((0.0, 0.0, 1.0),),
    )


def test_contact_scheduler_samples_exact_step_divisors() -> None:
    scheduler = ContactSensorScheduler(
        [_sensor("contact_100hz", 100.0), _sensor("contact_50hz", 50.0)],
        timestep=0.01,
    )
    home = {"contact_100hz": _empty(), "contact_50hz": _empty()}
    active = {"contact_100hz": _contact(), "contact_50hz": _contact()}

    initial = scheduler.reset(0.0, home)
    first = scheduler.capture(1, 0.01, active)
    second = scheduler.capture(2, 0.02, active)

    assert [(sample.sensor_id, sample.sequence) for sample in initial] == [
        ("contact_100hz", 0),
        ("contact_50hz", 0),
    ]
    assert [sample.sensor_id for sample in first] == ["contact_100hz"]
    assert [sample.sensor_id for sample in second] == ["contact_100hz", "contact_50hz"]
    assert scheduler.latest_samples[1].to_dict() == {
        "id": "contact_50hz",
        "sensor_type": "contact",
        "time": 0.02,
        "sequence": 1,
        "contact_count": 1,
        "normal_force": 12.0,
        "tangent_force": [1.0, -0.5, 0.0],
        "normal_impulse": 0.12,
        "points": [[0.1, 0.2, 0.3]],
        "normals": [[0.0, 0.0, 1.0]],
    }


@pytest.mark.parametrize("rate", [60.0, 101.0])
def test_contact_scheduler_rejects_non_divisor_rate(rate: float) -> None:
    with pytest.raises(ValueError, match="exact divisor"):
        ContactSensorScheduler([_sensor("contact", rate)], timestep=0.01)


def test_contact_measurement_rejects_unbounded_or_invalid_payload() -> None:
    with pytest.raises(ValueError, match="equal length"):
        ContactMeasurement(1, 1.0, (0.0, 0.0, 0.0), 0.01, ((0.0, 0.0, 0.0),))
    with pytest.raises(ValueError, match="at most 8"):
        ContactMeasurement(
            9,
            1.0,
            (0.0, 0.0, 0.0),
            0.01,
            ((0.0, 0.0, 0.0),) * 9,
            ((0.0, 0.0, 1.0),) * 9,
        )
    with pytest.raises(ValueError, match="normalized"):
        ContactMeasurement(
            1,
            1.0,
            (0.0, 0.0, 0.0),
            0.01,
            ((0.0, 0.0, 0.0),),
            ((0.0, 0.0, 2.0),),
        )
    with pytest.raises(ValueError, match="Empty contact"):
        ContactMeasurement(0, 1.0, (0.0, 0.0, 0.0), 0.0)


def test_contact_scheduler_requires_scope_aggregation_and_measurement() -> None:
    missing_scope = _sensor("missing_scope", 100.0)
    missing_scope.collider_id = None
    with pytest.raises(ValueError, match="exactly one scope"):
        ContactSensorScheduler([missing_scope], 0.01)

    invalid_aggregation = _sensor("invalid_aggregation", 100.0)
    invalid_aggregation.aggregation_mode = None
    with pytest.raises(ValueError, match="aggregation must be sum"):
        ContactSensorScheduler([invalid_aggregation], 0.01)

    scheduler = ContactSensorScheduler([_sensor("missing_value", 100.0)], 0.01)
    with pytest.raises(ValueError, match="Missing contact measurement"):
        scheduler.reset(0.0, {})
