from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from simlab.models.robotics import Sensor
from simlab.services.sensor_noise import SensorNoiseSampler


@dataclass(frozen=True, slots=True)
class JointKinematics:
    qpos: float
    qvel: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.qpos) or not math.isfinite(self.qvel):
            raise ValueError("Joint kinematics values must be finite")


@dataclass(frozen=True, slots=True)
class JointStateSensorSample:
    sensor_id: str
    joint_id: str
    time: float
    sequence: int
    qpos: float
    qvel: float

    def __post_init__(self) -> None:
        values = (self.time, self.qpos, self.qvel)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Joint state sensor sample values must be finite")
        if self.time < 0:
            raise ValueError("Joint state sensor sample time must be >= 0")
        if self.sequence < 0:
            raise ValueError("Joint state sensor sequence must be >= 0")

    def to_dict(self) -> dict[str, str | int | float]:
        return {
            "id": self.sensor_id,
            "sensor_type": "joint_state",
            "joint_id": self.joint_id,
            "time": self.time,
            "sequence": self.sequence,
            "qpos": self.qpos,
            "qvel": self.qvel,
        }


@dataclass(frozen=True, slots=True)
class _SensorBinding:
    sensor_id: str
    joint_id: str
    period_steps: int
    noise: SensorNoiseSampler


class JointStateSensorScheduler:
    """Sample joint-state sensors on exact fixed-physics-step divisors."""

    def __init__(self, sensors: Sequence[Sensor], timestep: float) -> None:
        self.timestep = float(timestep)
        if not math.isfinite(self.timestep) or self.timestep <= 0:
            raise ValueError("Sensor scheduler timestep must be finite and > 0")
        physics_rate = 1.0 / self.timestep
        bindings: list[_SensorBinding] = []
        for sensor in sensors:
            if sensor.sensor_type != "joint_state":
                continue
            if not sensor.joint_id:
                raise ValueError(f"Joint state sensor requires joint_id: {sensor.id}")
            update_rate = (
                physics_rate if sensor.update_rate_hz is None else sensor.update_rate_hz
            )
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
                _SensorBinding(
                    sensor_id=sensor.id,
                    joint_id=sensor.joint_id,
                    period_steps=period_steps,
                    noise=SensorNoiseSampler(sensor.id, sensor.noise),
                )
            )
        self._bindings = tuple(bindings)
        self._sequences = {binding.sensor_id: 0 for binding in self._bindings}
        self._latest: dict[str, JointStateSensorSample] = {}

    @property
    def latest_samples(self) -> tuple[JointStateSensorSample, ...]:
        return tuple(
            self._latest[binding.sensor_id]
            for binding in self._bindings
            if binding.sensor_id in self._latest
        )

    def reset(
        self,
        time: float,
        joints: Mapping[str, JointKinematics],
    ) -> tuple[JointStateSensorSample, ...]:
        self._sequences = {binding.sensor_id: 0 for binding in self._bindings}
        self._latest.clear()
        for binding in self._bindings:
            binding.noise.reset()
        emitted = tuple(self._sample(binding, time, joints, 0) for binding in self._bindings)
        self._latest.update({sample.sensor_id: sample for sample in emitted})
        return emitted

    def capture(
        self,
        physics_step: int,
        time: float,
        joints: Mapping[str, JointKinematics],
    ) -> tuple[JointStateSensorSample, ...]:
        if physics_step < 1:
            raise ValueError("Sensor scheduler physics_step must be >= 1")
        emitted: list[JointStateSensorSample] = []
        for binding in self._bindings:
            if physics_step % binding.period_steps != 0:
                continue
            sequence = self._sequences[binding.sensor_id] + 1
            self._sequences[binding.sensor_id] = sequence
            sample = self._sample(binding, time, joints, sequence)
            self._latest[binding.sensor_id] = sample
            emitted.append(sample)
        return tuple(emitted)

    def _sample(
        self,
        binding: _SensorBinding,
        time: float,
        joints: Mapping[str, JointKinematics],
        sequence: int,
    ) -> JointStateSensorSample:
        state = joints.get(binding.joint_id)
        if state is None:
            raise ValueError(
                f"Joint state sensor {binding.sensor_id} references unknown joint: "
                f"{binding.joint_id}"
            )
        return JointStateSensorSample(
            sensor_id=binding.sensor_id,
            joint_id=binding.joint_id,
            time=float(time),
            sequence=sequence,
            qpos=binding.noise.scalar("qpos", state.qpos),
            qvel=binding.noise.scalar("qvel", state.qvel),
        )
