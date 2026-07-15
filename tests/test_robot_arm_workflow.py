from __future__ import annotations

import math

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.openusd_importer import import_openusd_asset
from simlab.services.physics_validation import run_physics_preflight
from simlab.services.project_service import load_scene, save_scene
from simlab.services.simulation_session import MuJoCoSimulationSession


def test_external_usd_robot_round_trip_and_control_workflow(tmp_path) -> None:
    pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda",
        tmp_path,
    )
    assert imported.robotics_model is not None
    scene = Scene(
        name="External USD Robot Gate",
        actors=[
            Actor(
                id="actor_external_arm",
                name="External Two Joint Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
    )

    scene_path = tmp_path / "projects" / "robot_gate" / "scene.json"
    save_scene(scene_path, scene)
    reopened = load_scene(scene_path)
    report = run_physics_preflight(reopened, asset_root=tmp_path)

    assert report.is_valid
    assert reopened.to_dict() == scene.to_dict()
    source_path = tmp_path / reopened.actors[0].properties["source"]
    assert source_path.is_file()

    session = MuJoCoSimulationSession(
        reopened,
        tmp_path / "exports" / "robot_gate.xml",
        asset_root=tmp_path,
    )
    articulation = reopened.robotics.articulations[0]
    shoulder, elbow = articulation.joints
    initial = session.state()
    initial_links = {link.actor_id: link.position for link in initial.links}

    commanded = session.set_joint_position_targets(
        {shoulder.id: 0.8, elbow.id: -1.0}
    )
    moved = session.step(steps=300)
    moved_links = {link.actor_id: link.position for link in moved.links}

    assert [state.ctrl for state in commanded.actuators] == pytest.approx([0.8, -1.0])
    assert moved.joints[0].qpos == pytest.approx(0.8, abs=0.1)
    assert moved.joints[1].qpos == pytest.approx(-1.0, abs=0.1)
    assert [state.qvel for state in moved.joints] == pytest.approx([0.0, 0.0], abs=1e-3)
    assert any(
        math.dist(initial_links[link_id], moved_links[link_id]) > 0.01
        for link_id in initial_links
    )
    assert all(
        math.isfinite(value)
        for link in moved.links
        for value in (*link.position, *link.quaternion)
    )

    limited = session.set_joint_position_targets(
        {shoulder.id: 99.0, elbow.id: -99.0}
    )
    assert [state.ctrl for state in limited.actuators] == pytest.approx(
        [shoulder.limits.upper, elbow.limits.lower]
    )

    reset = session.reset()
    assert reset.time == 0
    assert [state.qpos for state in reset.joints] == pytest.approx(
        [shoulder.initial_position, elbow.initial_position]
    )
    assert [state.ctrl for state in reset.actuators] == pytest.approx(
        [shoulder.initial_position, elbow.initial_position]
    )
