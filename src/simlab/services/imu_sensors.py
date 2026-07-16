from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from simlab.models.robotics import Sensor

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


def _finite(values: tuple[float, ...], field_name: str) -> None:
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"IMU {field_name} values must be finite")


@dataclass(frozen=True, slots=True)
class ImuKinematics:
    """Sensor-frame IMU values with a world-from-sensor xyzw orientation."""

    orientation: Quaternion
    angular_velocity: Vector3
    linear_acceleration: Vector3

    def __post_init__(self) -> None:
        _finite(self.orientation, "orientation")
        _finite(self.angular_velocity, "angular velocity")
        _finite(self.linear_acceleration, "linear acceleration")
        norm = math.sqrt(sum(value * value for value in self.orientation))
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("IMU orientation quaternion must be normalized")


@dataclass(frozen=True, slots=True)
class ImuSensorSample:
    sensor_id: str
    link_id: str
    time: float
    sequence: int
    orientation: Quaternion
    angular_velocity: Vector3
    linear_acceleration: Vector3

    def __post_init__(self) -> None:
        if not math.isfinite(self.time) or self.time < 0:
            raise ValueError("IMU sample time must be finite and >= 0")
        if self.sequence < 0:
            raise ValueError("IMU sample sequence must be >= 0")
        ImuKinematics(
            orientation=self.orientation,
            angular_velocity=self.angular_velocity,
            linear_acceleration=self.linear_acceleration,
        )

    def to_dict(self) -> dict[str, str | int | float | list[float]]:
        return {
            "id": self.sensor_id,
            "sensor_type": "imu",
            "link_id": self.link_id,
            "time": self.time,
            "sequence": self.sequence,
            "orientation": list(self.orientation),
            "angular_velocity": list(self.angular_velocity),
            "linear_acceleration": list(self.linear_acceleration),
        }


@dataclass(frozen=True, slots=True)
class _ImuBinding:
    sensor_id: str
    link_id: str
    period_steps: int


class ImuSensorScheduler:
    """Publish precomputed sensor-frame IMU values on fixed-step divisors."""

    def __init__(self, sensors: Sequence[Sensor], timestep: float) -> None:
        self.timestep = float(timestep)
        if not math.isfinite(self.timestep) or self.timestep <= 0:
            raise ValueError("IMU scheduler timestep must be finite and > 0")
        physics_rate = 1.0 / self.timestep
        bindings: list[_ImuBinding] = []
        for sensor in sensors:
            if sensor.sensor_type != "imu":
                continue
            if not sensor.link_id:
                raise ValueError(f"IMU sensor requires link_id: {sensor.id}")
            if sensor.local_transform is None:
                raise ValueError(f"IMU sensor requires local_transform: {sensor.id}")
            update_rate = physics_rate if sensor.update_rate_hz is None else sensor.update_rate_hz
            ratio = physics_rate / update_rate
            period_steps = round(ratio)
            if period_steps < 1 or not math.isclose(
                ratio, period_steps, rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError(
                    f"Sensor {sensor.id} update_rate_hz must be an exact divisor "
                    f"of physics rate {physics_rate:g} Hz"
                )
            bindings.append(_ImuBinding(sensor.id, sensor.link_id, period_steps))
        self._bindings = tuple(bindings)
        self._sequences = {binding.sensor_id: 0 for binding in bindings}
        self._latest: dict[str, ImuSensorSample] = {}

    @property
    def latest_samples(self) -> tuple[ImuSensorSample, ...]:
        return tuple(
            self._latest[binding.sensor_id]
            for binding in self._bindings
            if binding.sensor_id in self._latest
        )

    def reset(
        self,
        time: float,
        measurements: Mapping[str, ImuKinematics],
    ) -> tuple[ImuSensorSample, ...]:
        self._sequences = {binding.sensor_id: 0 for binding in self._bindings}
        self._latest.clear()
        emitted = tuple(
            self._sample(binding, time, measurements, 0) for binding in self._bindings
        )
        self._latest.update({sample.sensor_id: sample for sample in emitted})
        return emitted

    def capture(
        self,
        physics_step: int,
        time: float,
        measurements: Mapping[str, ImuKinematics],
    ) -> tuple[ImuSensorSample, ...]:
        if physics_step < 1:
            raise ValueError("IMU scheduler physics_step must be >= 1")
        emitted: list[ImuSensorSample] = []
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
        binding: _ImuBinding,
        time: float,
        measurements: Mapping[str, ImuKinematics],
        sequence: int,
    ) -> ImuSensorSample:
        measurement = measurements.get(binding.sensor_id)
        if measurement is None:
            raise ValueError(f"Missing IMU measurement for sensor: {binding.sensor_id}")
        return ImuSensorSample(
            sensor_id=binding.sensor_id,
            link_id=binding.link_id,
            time=float(time),
            sequence=sequence,
            orientation=measurement.orientation,
            angular_velocity=measurement.angular_velocity,
            linear_acceleration=measurement.linear_acceleration,
        )
