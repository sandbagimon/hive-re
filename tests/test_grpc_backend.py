from __future__ import annotations

# ruff: noqa: E402 -- optional transport dependency must be checked before import.
import json
from pathlib import Path

import numpy as np
import pytest

grpc = pytest.importorskip("grpc")

from simlab.models.actor import Actor
from simlab.models.robotics import RoboticsModel
from simlab.models.scene import Scene
from simlab.simulation.backend import SceneBundle, SimulationBackendError
from simlab.simulation.grpc_backend import (
    GrpcSimulationBackend,
    create_grpc_server,
)
from simlab.simulation.gym_env import SimLabEnv
from simlab.simulation.robot_adapter import DirectActuatorAdapter
from simlab.simulation.task import JointTargetTask


def _robot_scene() -> Scene:
    robotics = RoboticsModel.from_dict(
        json.loads(Path("tests/fixtures/robotics/two_joint_arm.json").read_text(encoding="utf-8"))
    )
    return Scene(
        name="Remote Algorithm Arm",
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id="two_joint_arm",
                properties={"articulation_ids": ["arm_demo"]},
            )
        ],
        robotics=robotics,
        simulation_config={"timestep": 0.01},
    )


def test_same_gym_environment_runs_over_grpc_without_engine_imports_in_algorithm(
    tmp_path,
) -> None:
    pytest.importorskip("mujoco")
    server, port, servicer = create_grpc_server("127.0.0.1:0", token="secret")
    server.start()
    backend = GrpcSimulationBackend(f"127.0.0.1:{port}", token="secret")
    env = SimLabEnv(
        backend=backend,
        scene_bundle=SceneBundle.from_scene(
            _robot_scene(),
            export_path=tmp_path / "remote" / "scene.xml",
        ),
        task=JointTargetTask(
            robot=DirectActuatorAdapter(["actuator_shoulder", "actuator_elbow"]),
            target_positions=(0.6, -1.0),
            max_episode_steps=10,
        ),
        frame_skip=5,
    )
    try:
        observation, info = env.reset(seed=42)
        next_observation, reward, terminated, truncated, step_info = env.step(
            np.asarray([0.4, 0.0], dtype=np.float32)
        )

        assert observation.shape == (6,)
        assert next_observation.shape == (6,)
        assert info["joint_ids"] == ["joint_shoulder", "joint_elbow"]
        assert reward < 0.0
        assert terminated is False
        assert truncated is False
        assert step_info["physics_step"] == 5
        assert env.model_description.backend_name == "mujoco-local"
    finally:
        env.close()
        backend.close()
        servicer.close_all()
        server.stop(0).wait()


def test_grpc_backend_rejects_missing_access_token() -> None:
    server, port, servicer = create_grpc_server("127.0.0.1:0", token="secret")
    server.start()
    backend = GrpcSimulationBackend(f"127.0.0.1:{port}", timeout=2.0)
    try:
        with pytest.raises(SimulationBackendError, match="UNAUTHENTICATED"):
            backend.create_session(SceneBundle.from_scene(Scene()))
    finally:
        backend.close()
        servicer.close_all()
        server.stop(0).wait()
