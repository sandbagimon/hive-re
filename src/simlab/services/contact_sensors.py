from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from simlab.models.robotics import Sensor

Vector3 = tuple[float, float, float]
MAX_CONTACT_POINTS = 8


def _validate_vector(vector: Vector3, field_name: str) -> None:
    if any(not math.isfinite(value) for value in vector):
        raise ValueError(f"Contact {field_name} values must be finite")


@dataclass(frozen=True, slots=True)
class ContactMeasurement:
    """Aggregated contact values; vectors and points are expressed in world frame."""

    contact_count: int
    normal_force: float
    tangent_force: Vector3
    normal_impulse: float
    points: tuple[Vector3, ...] = ()
    normals: tuple[Vector3, ...] = ()

    def __post_init__(self) -> None:
        if self.contact_count < 0:
            raise ValueError("Contact count must be >= 0")
        if len(self.points) != len(self.normals):
            raise ValueError("Contact points and normals must have equal length")
        if len(self.points) > MAX_CONTACT_POINTS:
            raise ValueError(f"Contact payload supports at most {MAX_CONTACT_POINTS} points")
        if self.contact_count < len(self.points):
            raise ValueError("Contact count cannot be smaller than retained point count")
        scalars = (self.normal_force, self.normal_impulse)
        if any(not math.isfinite(value) or value < 0 for value in scalars):
            raise ValueError("Contact normal force and impulse must be finite and >= 0")
        _validate_vector(self.tangent_force, "tangent force")
        for point in self.points:
            _validate_vector(point, "point")
        for normal in self.normals:
            _validate_vector(normal, "normal")
            norm = math.sqrt(sum(value * value for value in normal))
            if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("Contact normals must be normalized")
        if self.contact_count == 0 and (
            self.normal_force != 0
            or self.normal_impulse != 0
            or any(self.tangent_force)
            or self.points
        ):
            raise ValueError("Empty contact measurement must have zero force and no points")


@dataclass(frozen=True, slots=True)
class ContactSensorSample:
    sensor_id: str
    time: float
    sequence: int
    measurement: ContactMeasurement

    def __post_init__(self) -> None:
        if not math.isfinite(self.time) or self.time < 0:
            raise ValueError("Contact sample time must be finite and >= 0")
        if self.sequence < 0:
            raise ValueError("Contact sample sequence must be >= 0")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.sensor_id,
            "sensor_type": "contact",
            "time": self.time,
            "sequence": self.sequence,
            "contact_count": self.measurement.contact_count,
            "normal_force": self.measurement.normal_force,
            "tangent_force": list(self.measurement.tangent_force),
            "normal_impulse": self.measurement.normal_impulse,
            "points": [list(point) for point in self.measurement.points],
            "normals": [list(normal) for normal in self.measurement.normals],
        }


@dataclass(frozen=True, slots=True)
class _ContactBinding:
    sensor_id: str
    period_steps: int


class ContactSensorScheduler:
    """Publish pre-aggregated contact measurements on fixed-step divisors."""

    def __init__(self, sensors: Sequence[Sensor], timestep: float) -> None:
        self.timestep = float(timestep)
        if not math.isfinite(self.timestep) or self.timestep <= 0:
            raise ValueError("Contact scheduler timestep must be finite and > 0")
        physics_rate = 1.0 / self.timestep
        bindings: list[_ContactBinding] = []
        for sensor in sensors:
            if sensor.sensor_type != "contact":
                continue
            scope_count = int(sensor.link_id is not None) + int(
                sensor.collider_id is not None
            )
            if scope_count != 1:
                raise ValueError(
                    f"Contact sensor requires exactly one scope: {sensor.id}"
                )
            if sensor.aggregation_mode != "sum":
                raise ValueError(f"Contact sensor aggregation must be sum: {sensor.id}")
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
            bindings.append(_ContactBinding(sensor.id, period_steps))
        self._bindings = tuple(bindings)
        self._sequences = {binding.sensor_id: 0 for binding in bindings}
        self._latest: dict[str, ContactSensorSample] = {}

    @property
    def latest_samples(self) -> tuple[ContactSensorSample, ...]:
        return tuple(
            self._latest[binding.sensor_id]
            for binding in self._bindings
            if binding.sensor_id in self._latest
        )

    def reset(
        self,
        time: float,
        measurements: Mapping[str, ContactMeasurement],
    ) -> tuple[ContactSensorSample, ...]:
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
        measurements: Mapping[str, ContactMeasurement],
    ) -> tuple[ContactSensorSample, ...]:
        if physics_step < 1:
            raise ValueError("Contact scheduler physics_step must be >= 1")
        emitted: list[ContactSensorSample] = []
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
        binding: _ContactBinding,
        time: float,
        measurements: Mapping[str, ContactMeasurement],
        sequence: int,
    ) -> ContactSensorSample:
        measurement = measurements.get(binding.sensor_id)
        if measurement is None:
            raise ValueError(f"Missing contact measurement for sensor: {binding.sensor_id}")
        return ContactSensorSample(
            sensor_id=binding.sensor_id,
            time=float(time),
            sequence=sequence,
            measurement=measurement,
        )
