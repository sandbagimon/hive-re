from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from simlab.models.scene import Scene
from simlab.simulation.backend import (
    ActuatorDescription,
    BackendState,
    BodyDescription,
    ControlCommand,
    JointDescription,
    ModelDescription,
    ResetOptions,
    SceneBundle,
)
from simlab.simulation.backend_factory import BackendConfig, create_backend
from simlab.simulation.gym_env import SimLabEnv
from simlab.simulation.robot_adapter import DirectActuatorAdapter
from simlab.simulation.task import JointTargetTask

gymnasium = pytest.importorskip("gymnasium")

DESCRIPTION = ModelDescription(
    backend_name="test",
    backend_version="1",
    timestep=0.01,
    scene_hash="scene",
    schema_hash="schema",
    bodies=(BodyDescription("base"),),
    joints=(
        JointDescription("shoulder", -1.0, 1.0),
        JointDescription("elbow", -2.0, 0.0),
    ),
    actuators=(
        ActuatorDescription("shoulder_drive", "shoulder", "position", -1.0, 1.0),
        ActuatorDescription("elbow_drive", "elbow", "position", -2.0, 0.0),
    ),
)


@dataclass
class FakeSession:
    offset: float = 0.0
    closed: bool = False

    @property
    def model_description(self) -> ModelDescription:
        return DESCRIPTION

    def reset(
        self,
        *,
        seed: int | None = None,
        options: ResetOptions | None = None,
    ) -> BackendState:
        del seed
        positions = [self.offset, -0.4]
        controls = [0.0, -0.4]
        for identifier, value in (options or ResetOptions()).joint_positions.items():
            positions[{"shoulder": 0, "elbow": 1}[identifier]] = value
        for identifier, value in (options or ResetOptions()).actuator_controls.items():
            controls[{"shoulder_drive": 0, "elbow_drive": 1}[identifier]] = value
        self.state = BackendState(
            schema_hash="schema",
            time=0.0,
            step_index=0,
            joint_positions=tuple(positions),
            joint_velocities=(0.0, 0.0),
            actuator_controls=tuple(controls),
            actuator_forces=(0.0, 0.0),
            body_positions=((0.0, 0.0, 0.0),),
            body_quaternions=((1.0, 0.0, 0.0, 0.0),),
            body_linear_velocities=((0.0, 0.0, 0.0),),
            body_angular_velocities=((0.0, 0.0, 0.0),),
        )
        return self.state

    def step(self, command: ControlCommand, *, physics_steps: int = 1) -> BackendState:
        old = self.state
        positions = tuple(
            current + 0.5 * (control - current)
            for current, control in zip(old.joint_positions, command.values, strict=True)
        )
        self.state = BackendState(
            schema_hash="schema",
            time=old.time + physics_steps * DESCRIPTION.timestep,
            step_index=old.step_index + physics_steps,
            joint_positions=positions,
            joint_velocities=tuple(
                (new - previous) / (physics_steps * DESCRIPTION.timestep)
                for new, previous in zip(positions, old.joint_positions, strict=True)
            ),
            actuator_controls=command.values,
            actuator_forces=(0.0, 0.0),
            body_positions=old.body_positions,
            body_quaternions=old.body_quaternions,
            body_linear_velocities=old.body_linear_velocities,
            body_angular_velocities=old.body_angular_velocities,
        )
        return self.state

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeBackend:
    offset: float = 0.0

    def create_session(self, bundle: SceneBundle) -> FakeSession:
        del bundle
        self.session = FakeSession(self.offset)
        return self.session


def _make_env(backend: FakeBackend) -> SimLabEnv:
    return SimLabEnv(
        backend=backend,
        scene_bundle=SceneBundle.from_scene(Scene()),
        task=JointTargetTask(
            robot=DirectActuatorAdapter(["shoulder_drive", "elbow_drive"]),
            target_positions=(0.5, -1.0),
            max_episode_steps=2,
            terminate_on_success=False,
        ),
        frame_skip=4,
        render_mode="state",
    )


def test_gym_environment_has_standard_spaces_and_atomic_steps() -> None:
    backend = FakeBackend()
    env = _make_env(backend)

    observation, reset_info = env.reset(seed=123)
    next_observation, reward, terminated, truncated, info = env.step(
        np.asarray([0.5, 0.0], dtype=np.float32)
    )

    assert env.action_space.shape == (2,)
    assert env.observation_space.shape == (6,)
    assert env.observation_space.contains(observation)
    assert env.observation_space.contains(next_observation)
    assert reset_info["joint_ids"] == ["shoulder", "elbow"]
    assert reward < 0.0
    assert terminated is False
    assert truncated is False
    assert info["physics_step"] == 4
    assert env.render().step_index == 4

    _, _, _, truncated, _ = env.step(np.zeros(2, dtype=np.float32))
    assert truncated is True
    env.close()
    assert backend.session.closed is True
    with pytest.raises(RuntimeError, match="closed"):
        env.reset()


def test_same_task_switches_backend_without_algorithm_changes() -> None:
    observations = []
    for backend in (FakeBackend(offset=0.0), FakeBackend(offset=0.2)):
        env = _make_env(backend)
        observation, _ = env.reset(seed=9)
        observations.append(observation)
        env.close()

    assert observations[0][0] == pytest.approx(0.0)
    assert observations[1][0] == pytest.approx(0.2)


def test_gymnasium_checker_accepts_simlab_environment() -> None:
    from gymnasium.utils.env_checker import check_env

    env = _make_env(FakeBackend())
    check_env(env, skip_render_check=True)
    env.close()


def test_task_randomization_replays_from_gym_seed() -> None:
    env = SimLabEnv(
        backend=FakeBackend(),
        scene_bundle=SceneBundle.from_scene(Scene()),
        task=JointTargetTask(
            robot=DirectActuatorAdapter(["shoulder_drive", "elbow_drive"]),
            target_positions=(0.0, -1.0),
            random_target_ranges=((-0.5, 0.5), (-1.5, -0.5)),
        ),
    )

    first, first_info = env.reset(seed=2026)
    second, second_info = env.reset(seed=2026)

    assert second == pytest.approx(first)
    assert second_info["target_positions"] == pytest.approx(first_info["target_positions"])
    env.close()


def test_backend_selection_is_configuration_only() -> None:
    backend = create_backend(BackendConfig(kind="local"))
    remote = create_backend({"kind": "grpc", "target": "127.0.0.1:50051", "timeout": 1.0})

    assert type(backend).__name__ == "MujocoBackend"
    assert type(remote).__name__ == "GrpcSimulationBackend"
    remote.close()
