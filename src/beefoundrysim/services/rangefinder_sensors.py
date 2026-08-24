from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from beefoundrysim.models.robotics import Sensor
from beefoundrysim.services.sensor_noise import SensorNoiseSampler


@dataclass(frozen=True, slots=True)
class RangefinderMeasurement:
    distance: float
    hit: bool

    def __post_init__(self) -> None:
        if not math.isfinite(self.distance) or self.distance < 0:
            raise ValueError("Rangefinder distance must be finite and >= 0")


@dataclass(frozen=True, slots=True)
class RangefinderSensorSample:
    sensor_id: str
    link_id: str
    time: float
    sequence: int
    distance: float
    max_distance: float
    hit: bool

    def __post_init__(self) -> None:
        values = (self.time, self.distance, self.max_distance)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Rangefinder sample values must be finite")
        if self.time < 0 or self.distance < 0 or self.max_distance <= 0:
            raise ValueError("Rangefinder time/distance bounds are invalid")
        if self.distance > self.max_distance:
            raise ValueError("Rangefinder distance cannot exceed max_distance")
        if self.sequence < 0:
            raise ValueError("Rangefinder sample sequence must be >= 0")

    def to_dict(self) -> dict[str, str | int | float | bool]:
        return {
            "id": self.sensor_id,
            "sensor_type": "rangefinder",
            "link_id": self.link_id,
            "time": self.time,
            "sequence": self.sequence,
            "distance": self.distance,
            "max_distance": self.max_distance,
            "hit": self.hit,
        }


@dataclass(frozen=True, slots=True)
class _RangefinderBinding:
    sensor_id: str
    link_id: str
    max_distance: float
    period_steps: int
    noise: SensorNoiseSampler


class RangefinderSensorScheduler:
    """Publish bounded ray distances on exact fixed-physics-step divisors."""

    def __init__(self, sensors: Sequence[Sensor], timestep: float) -> None:
        self.timestep = float(timestep)
        if not math.isfinite(self.timestep) or self.timestep <= 0:
            raise ValueError("Rangefinder scheduler timestep must be finite and > 0")
        physics_rate = 1.0 / self.timestep
        bindings: list[_RangefinderBinding] = []
        for sensor in sensors:
            if sensor.sensor_type != "rangefinder":
                continue
            if not sensor.link_id:
                raise ValueError(f"Rangefinder sensor requires link_id: {sensor.id}")
            if sensor.local_transform is None:
                raise ValueError(f"Rangefinder sensor requires local_transform: {sensor.id}")
            if sensor.max_distance is None or not math.isfinite(sensor.max_distance):
                raise ValueError(f"Rangefinder sensor requires finite max_distance: {sensor.id}")
            if sensor.max_distance <= 0:
                raise ValueError(f"Rangefinder max_distance must be > 0: {sensor.id}")
            update_rate = physics_rate if sensor.update_rate_hz is None else sensor.update_rate_hz
            if not math.isfinite(update_rate) or update_rate <= 0:
                raise ValueError(
                    f"Sensor {sensor.id} update_rate_hz must be finite and > 0"
                )
            ratio = physics_rate / update_rate
            period_steps = round(ratio)
            if period_steps < 1 or not math.isclose(
                ratio, period_steps, rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError(
                    f"Sensor {sensor.id} update_rate_hz must be an exact divisor "
                    f"of physics rate {physics_rate:g} Hz"
                )
            bindings.append(
                _RangefinderBinding(
                    sensor_id=sensor.id,
                    link_id=sensor.link_id,
                    max_distance=sensor.max_distance,
                    period_steps=period_steps,
                    noise=SensorNoiseSampler(sensor.id, sensor.noise),
                )
            )
        self._bindings = tuple(bindings)
        self._sequences = {binding.sensor_id: 0 for binding in bindings}
        self._latest: dict[str, RangefinderSensorSample] = {}

    @property
    def latest_samples(self) -> tuple[RangefinderSensorSample, ...]:
        return tuple(
            self._latest[binding.sensor_id]
            for binding in self._bindings
            if binding.sensor_id in self._latest
        )

    def reset(
        self,
        time: float,
        measurements: Mapping[str, RangefinderMeasurement],
    ) -> tuple[RangefinderSensorSample, ...]:
        self._sequences = {binding.sensor_id: 0 for binding in self._bindings}
        self._latest.clear()
        for binding in self._bindings:
            binding.noise.reset()
        emitted = tuple(
            self._sample(binding, time, measurements, 0) for binding in self._bindings
        )
        self._latest.update({sample.sensor_id: sample for sample in emitted})
        return emitted

    def capture(
        self,
        physics_step: int,
        time: float,
        measurements: Mapping[str, RangefinderMeasurement],
    ) -> tuple[RangefinderSensorSample, ...]:
        if physics_step < 1:
            raise ValueError("Rangefinder scheduler physics_step must be >= 1")
        emitted: list[RangefinderSensorSample] = []
        for binding in self._bindings:
            if physics_step % binding.period_steps != 0:
                continue
            sequence = self._sequences[binding.sensor_id] + 1
            self._sequences[binding.sensor_id] = sequence
            sample = self._sample(binding, time, measurements, sequence)
            self._latest[binding.sensor_id] = sample
            emitted.append(sample)
        return tuple(emitted)

    @staticmethod
    def _sample(
        binding: _RangefinderBinding,
        time: float,
        measurements: Mapping[str, RangefinderMeasurement],
        sequence: int,
    ) -> RangefinderSensorSample:
        measurement = measurements.get(binding.sensor_id)
        if measurement is None:
            raise ValueError(
                f"Missing rangefinder measurement for sensor: {binding.sensor_id}"
            )
        distance = measurement.distance
        if measurement.hit:
            distance = binding.noise.scalar("distance", distance)
        distance = max(0.0, min(binding.max_distance, distance))
        return RangefinderSensorSample(
            sensor_id=binding.sensor_id,
            link_id=binding.link_id,
            time=float(time),
            sequence=sequence,
            distance=distance,
            max_distance=binding.max_distance,
            hit=measurement.hit,
        )
