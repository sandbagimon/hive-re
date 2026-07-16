from simlab.models.robotics import SensorNoise, SensorNoiseChannel
from simlab.services.sensor_noise import SensorNoiseSampler


def _noise() -> SensorNoise:
    return SensorNoise(
        seed=1234,
        channels={
            "qpos": SensorNoiseChannel(bias=0.1, standard_deviation=0.01),
            "angular_velocity": SensorNoiseChannel(
                bias=[0.1, -0.2, 0.3],
                standard_deviation=[0.01, 0.02, 0.03],
            ),
        },
    )


def test_sensor_noise_reset_replays_same_per_channel_sequence() -> None:
    sampler = SensorNoiseSampler("sensor_arm", _noise())

    first = [sampler.scalar("qpos", 1.0) for _ in range(4)]
    sampler.reset()
    replay = [sampler.scalar("qpos", 1.0) for _ in range(4)]

    assert replay == first
    assert first != [1.1] * 4


def test_sensor_noise_streams_are_stable_and_independent() -> None:
    first = SensorNoiseSampler("sensor_arm", _noise())
    second = SensorNoiseSampler("sensor_arm", _noise())
    other = SensorNoiseSampler("sensor_other", _noise())

    first.vector("angular_velocity", [0.0, 0.0, 0.0])

    assert first.scalar("qpos", 0.0) == second.scalar("qpos", 0.0)
    assert first.scalar("qpos", 0.0) != other.scalar("qpos", 0.0)


def test_sensor_noise_bias_and_zero_stddev_are_exact() -> None:
    noise = SensorNoise(
        seed=0,
        channels={
            "tangent_force": SensorNoiseChannel(
                bias=[1.0, -2.0, 3.0],
                standard_deviation=[0.0, 0.0, 0.0],
            )
        },
    )

    assert SensorNoiseSampler("contact", noise).vector(
        "tangent_force", [4.0, 5.0, 6.0]
    ) == (5.0, 3.0, 9.0)


def test_sensor_noise_absent_channels_preserve_exact_values() -> None:
    sampler = SensorNoiseSampler("exact", None)

    assert sampler.scalar("qpos", 1.25) == 1.25
    assert sampler.vector("angular_velocity", [1.0, 2.0, 3.0]) == (1.0, 2.0, 3.0)
