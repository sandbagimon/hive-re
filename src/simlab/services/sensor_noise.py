from __future__ import annotations

import hashlib
from collections.abc import Sequence

import numpy as np

from simlab.models.robotics import SensorNoise, SensorNoiseChannel


class SensorNoiseSampler:
    """Deterministic per-sensor, per-channel Gaussian white-noise streams."""

    def __init__(self, sensor_id: str, noise: SensorNoise | None) -> None:
        self.sensor_id = sensor_id
        self.noise = noise
        self._generators: dict[str, np.random.Generator] = {}
        self.reset()

    def reset(self) -> None:
        self._generators = {}
        if self.noise is None:
            return
        for channel in self.noise.channels:
            digest = hashlib.sha256(
                f"{self.noise.seed}\0{self.sensor_id}\0{channel}".encode()
            ).digest()
            seed = int.from_bytes(digest[:16], "little")
            self._generators[channel] = np.random.Generator(np.random.PCG64(seed))

    def scalar(self, channel: str, value: float) -> float:
        config = self._channel(channel)
        if config is None:
            return float(value)
        if isinstance(config.bias, list) or isinstance(
            config.standard_deviation, list
        ):
            raise ValueError(f"Sensor noise channel is not scalar: {channel}")
        noise = self._generators[channel].normal(0.0, config.standard_deviation)
        return float(value) + config.bias + float(noise)

    def vector(self, channel: str, values: Sequence[float]) -> tuple[float, ...]:
        config = self._channel(channel)
        source = np.asarray(values, dtype=np.float64)
        if config is None:
            return tuple(float(value) for value in source)
        if not isinstance(config.bias, list) or not isinstance(
            config.standard_deviation, list
        ):
            raise ValueError(f"Sensor noise channel is not a vector: {channel}")
        if len(source) != len(config.bias) or len(source) != len(
            config.standard_deviation
        ):
            raise ValueError(f"Sensor noise channel dimension mismatch: {channel}")
        noise = self._generators[channel].normal(
            np.zeros(len(source)),
            np.asarray(config.standard_deviation),
        )
        result = source + np.asarray(config.bias) + noise
        return tuple(float(value) for value in result)

    def _channel(self, channel: str) -> SensorNoiseChannel | None:
        if self.noise is None:
            return None
        return self.noise.channels.get(channel)
