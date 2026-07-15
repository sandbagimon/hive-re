from __future__ import annotations

import math

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.openusd_importer import import_openusd_asset
from simlab.services.simulation_session import MuJoCoSimulationSession, SimulationState


def _assert_finite_state(state: SimulationState, cycle: int) -> None:
    assert math.isfinite(state.time), f"cycle {cycle}: non-finite simulation time"
    for link in state.links:
        values = (*link.position, *link.quaternion)
        assert all(math.isfinite(value) for value in values), (
            f"cycle {cycle}: non-finite link pose for {link.actor_id}: {values}"
        )
        quaternion_norm = math.sqrt(sum(value * value for value in link.quaternion))
        assert quaternion_norm == pytest.approx(1.0, abs=1e-6), (
            f"cycle {cycle}: invalid quaternion for {link.actor_id}"
        )
    for joint in state.joints:
        assert math.isfinite(joint.qpos), (
            f"cycle {cycle}: non-finite qpos for {joint.joint_id}"
        )
        assert math.isfinite(joint.qvel), (
            f"cycle {cycle}: non-finite qvel for {joint.joint_id}"
        )
    for actuator in state.actuators:
        assert math.isfinite(actuator.ctrl), (
            f"cycle {cycle}: non-finite ctrl for {actuator.actuator_id}"
        )
        assert math.isfinite(actuator.force), (
            f"cycle {cycle}: non-finite force for {actuator.actuator_id}"
        )


def test_external_usd_robot_control_soak_stays_finite_and_within_limits(
    tmp_path,
) -> None:
    pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    scene = Scene(
        name="External Robot Soak",
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
        simulation_config={"timestep": 0.002},
    )
    session = MuJoCoSimulationSession(scene, tmp_path / "soak.xml", asset_root=tmp_path)
    articulation = imported.robotics_model.articulations[0]
    shoulder, elbow = articulation.joints
    target_sequence = [
        {shoulder.id: -1.2, elbow.id: -1.8},
        {shoulder.id: 1.2, elbow.id: -0.2},
        {shoulder.id: 0.0, elbow.id: -0.4},
        {shoulder.id: 0.7, elbow.id: -1.2},
    ]
    previous_time = 0.0
    observed_positions: list[tuple[float, float]] = []

    for cycle in range(40):
        target = target_sequence[cycle % len(target_sequence)]
        commanded = session.set_joint_position_targets(target)
        state = session.step(steps=50)
        _assert_finite_state(state, cycle)

        assert state.time > previous_time, f"cycle {cycle}: simulation time did not advance"
        previous_time = state.time
        assert [item.ctrl for item in commanded.actuators] == pytest.approx(
            [target[shoulder.id], target[elbow.id]]
        )
        for joint_model, joint_state in zip(articulation.joints, state.joints, strict=True):
            assert joint_model.limits is not None
            assert joint_model.limits.lower is not None
            assert joint_model.limits.upper is not None
            assert joint_model.limits.lower - 1e-6 <= joint_state.qpos
            assert joint_state.qpos <= joint_model.limits.upper + 1e-6
        for actuator_model, actuator_state in zip(
            articulation.actuators, state.actuators, strict=True
        ):
            assert actuator_model.max_force is not None
            assert abs(actuator_state.force) <= actuator_model.max_force + 1e-6
        observed_positions.append((state.joints[0].qpos, state.joints[1].qpos))

    assert previous_time == pytest.approx(4.0)
    assert math.dist(observed_positions[0], observed_positions[-1]) > 0.1
