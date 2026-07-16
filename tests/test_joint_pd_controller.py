from __future__ import annotations

import pytest

from simlab.controllers import JointPdConfig, JointPositionPdController
from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.controller_loader import ProjectControllerLoader
from simlab.services.controller_runtime import (
    ControllerObservation,
    JointObservation,
)
from simlab.services.openusd_importer import import_openusd_asset
from simlab.services.simulation_session import MuJoCoSimulationSession


def _observation(qpos: float, qvel: float = 0.0) -> ControllerObservation:
    return ControllerObservation(
        time=0.0,
        timestep=0.01,
        joints={"shoulder": JointObservation(qpos=qpos, qvel=qvel)},
        actuators={},
    )


def test_joint_pd_controller_bounds_outer_loop_target_and_updates_goal() -> None:
    controller = JointPositionPdController(
        {"shoulder": JointPdConfig(target=1.0, kp=0.5, kd=0.1, max_delta=0.05)}
    )
    controller.reset(_observation(0.0))

    rising = controller.step(_observation(0.0))
    damped = controller.step(_observation(0.4, qvel=2.0))
    controller.set_target("shoulder", -0.5)
    falling = controller.step(_observation(0.4))

    assert rising.position_targets["shoulder"] == pytest.approx(0.05)
    assert damped.position_targets["shoulder"] == pytest.approx(0.45)
    assert falling.position_targets["shoulder"] == pytest.approx(0.35)
    assert controller.configs["shoulder"].target == -0.5
    assert controller.last_reset_time == 0.0


def test_joint_pd_controller_rejects_invalid_config_and_observation() -> None:
    with pytest.raises(ValueError, match="kp"):
        JointPdConfig(target=0.0, kp=0.0)
    with pytest.raises(ValueError, match="at least one"):
        JointPositionPdController({})

    controller = JointPositionPdController({"missing": JointPdConfig(target=0.0)})
    with pytest.raises(ValueError, match="missing configured joints"):
        controller.reset(_observation(0.0))
    with pytest.raises(ValueError, match="unknown joint"):
        controller.set_target("other", 1.0)


def test_two_joint_pd_project_example_uses_observation_joint_ids() -> None:
    loaded = ProjectControllerLoader(".").load("examples/controllers/two_joint_pd.py")
    observation = ControllerObservation(
        time=0.0,
        timestep=0.01,
        joints={
            "axis_a": JointObservation(qpos=0.1, qvel=0.0),
            "axis_b": JointObservation(qpos=-0.4, qvel=0.0),
        },
        actuators={},
    )

    loaded.controller.reset(observation)
    action = loaded.controller.step(observation)

    assert loaded.name == "Two Joint PD Example"
    assert action is not None
    assert action.position_targets == pytest.approx({"axis_a": 0.14, "axis_b": -0.44})


def test_joint_pd_controller_drives_external_robot_deterministically(tmp_path) -> None:
    pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    articulation = imported.robotics_model.articulations[0]
    shoulder, elbow = articulation.joints
    scene = Scene(
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
        simulation_config={"timestep": 0.01},
    )

    def run_once(name: str) -> list[tuple[float, float]]:
        controller = JointPositionPdController(
            {
                shoulder.id: JointPdConfig(target=0.6, kp=0.25, kd=0.01),
                elbow.id: JointPdConfig(target=-1.0, kp=0.25, kd=0.01),
            },
            name=name,
        )
        session = MuJoCoSimulationSession(
            scene,
            tmp_path / name / "scene.xml",
            asset_root=tmp_path,
        )
        session.attach_controller(controller)
        samples: list[tuple[float, float]] = []
        for _ in range(200):
            state = session.step()
            samples.append((state.joints[0].qpos, state.joints[1].qpos))
        assert state.controller.step_count == 200
        assert state.joints[0].qpos > 0.45
        assert state.joints[1].qpos < -0.8
        controller.set_target(shoulder.id, 99.0)
        limited = session.step(steps=100)
        assert limited.actuators[0].ctrl == pytest.approx(shoulder.limits.upper)
        assert limited.joints[0].qpos <= shoulder.limits.upper + 0.01
        return samples

    first = run_once("first")
    second = run_once("second")

    assert second == pytest.approx(first, abs=1e-12)
