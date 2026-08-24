from __future__ import annotations

import pytest

from beefoundrysim.models.robotics import RigidTransform, Sensor, SensorNoise, SensorNoiseChannel
from beefoundrysim.services.rangefinder_sensors import (
    RangefinderMeasurement,
    RangefinderSensorScheduler,
)


def _sensor(*, rate: float = 50.0, noisy: bool = False) -> Sensor:
    return Sensor(
        id="sensor_front",
        name="Front Range",
        sensor_type="rangefinder",
        link_id="body",
        update_rate_hz=rate,
        local_transform=RigidTransform(),
        max_distance=4.0,
        noise=(
            SensorNoise(
                seed=17,
                channels={
                    "distance": SensorNoiseChannel(bias=0.01, standard_deviation=0.005)
                },
            )
            if noisy
            else None
        ),
    )


def test_rangefinder_scheduler_samples_bounded_measurements_at_fixed_rate() -> None:
    scheduler = RangefinderSensorScheduler([_sensor()], timestep=0.01)
    measurement = {"sensor_front": RangefinderMeasurement(distance=1.25, hit=True)}

    initial = scheduler.reset(0.0, measurement)
    first = scheduler.capture(1, 0.01, measurement)
    second = scheduler.capture(2, 0.02, measurement)

    assert [(sample.sequence, sample.distance, sample.hit) for sample in initial] == [
        (0, 1.25, True)
    ]
    assert first == ()
    assert [(sample.sequence, sample.time) for sample in second] == [(1, 0.02)]
    assert scheduler.latest_samples[0].to_dict()["sensor_type"] == "rangefinder"


def test_rangefinder_no_hit_stays_at_max_range_without_noise() -> None:
    scheduler = RangefinderSensorScheduler([_sensor(noisy=True)], timestep=0.01)

    sample = scheduler.reset(
        0.0,
        {"sensor_front": RangefinderMeasurement(distance=4.0, hit=False)},
    )[0]

    assert sample.distance == 4.0
    assert sample.hit is False


def test_rangefinder_noise_sequence_replays_after_reset() -> None:
    scheduler = RangefinderSensorScheduler([_sensor(noisy=True)], timestep=0.01)
    measurement = {"sensor_front": RangefinderMeasurement(distance=1.0, hit=True)}

    first = scheduler.reset(0.0, measurement)[0].distance
    second = scheduler.capture(2, 0.02, measurement)[0].distance
    replay_first = scheduler.reset(0.0, measurement)[0].distance
    replay_second = scheduler.capture(2, 0.02, measurement)[0].distance

    assert (replay_first, replay_second) == (first, second)


@pytest.mark.parametrize("rate", [0.0, 33.0, 101.0])
def test_rangefinder_rejects_invalid_or_non_divisor_rate(rate: float) -> None:
    with pytest.raises(ValueError):
        RangefinderSensorScheduler([_sensor(rate=rate)], timestep=0.01)
