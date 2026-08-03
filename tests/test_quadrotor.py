from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from simlab.models.actor import Actor
from simlab.models.robotics import RoboticsModel
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.controller_loader import ProjectControllerLoader
from simlab.services.controller_runtime import ControllerAction
from simlab.services.project_service import ProjectValidationError, validate_scene
from simlab.services.quadrotor_dynamics import quadrotor_models_from_scene
from simlab.services.simulation_session import MuJoCoSimulationSession
from simlab.simulation.backend import SceneBundle
from simlab.simulation.mujoco_backend import MujocoBackend
from simlab.simulation.robot_adapter import QuadrotorAdapter

IRIS_ASSET_ID = "openusd_iris_09f8390b45"
IRIS_ACTUATORS = tuple(f"actuator_iris_rotor_{index}" for index in range(4))
IRIS_HOVER_TRIM = (641.132187, 679.039297, 646.466695, 673.962654)


def _iris_scene(*, height: float = 1.0) -> Scene:
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    asset = next(item for item in metadata["assets"] if item["id"] == IRIS_ASSET_ID)
    properties = asset["default_properties"]
    robotics = RoboticsModel.from_dict(
        json.loads(Path(properties["robotics_cache"]).read_text(encoding="utf-8"))
    )
    return Scene(
        name="Iris Quadrotor Test",
        actors=[
            Actor(
                id="actor_iris",
                name="Iris",
                type="robot",
                asset_id=IRIS_ASSET_ID,
                transform=Transform(position=[0.0, 0.0, height]),
                properties=properties,
            )
        ],
        robotics=robotics,
        simulation_config={"timestep": 0.002, "duration": 1.0},
    )


def test_iris_quadrotor_metadata_binds_four_rotors() -> None:
    scene = _iris_scene()
    model = quadrotor_models_from_scene(scene)[0]

    assert model.actor_id == "actor_iris"
    assert model.body_link_id == "link_c46480014a33"
    assert tuple(rotor.actuator_id for rotor in model.rotors) == IRIS_ACTUATORS
    assert tuple(rotor.direction for rotor in model.rotors) == (-1, -1, 1, 1)
    assert all(rotor.max_angular_velocity == 1100.0 for rotor in model.rotors)
    iris = scene.robotics.articulations[0]
    rotor_positions = {
        link.name: link.transform.position for link in iris.links if link.name.startswith("rotor")
    }
    expected_positions = {
        "rotor0": [0.13759533, -0.20673534, 0.023],
        "rotor1": [-0.12499997, 0.21869458, 0.023],
        "rotor2": [0.13830880, 0.20321965, 0.023],
        "rotor3": [-0.12450201, -0.22199887, 0.023],
    }
    assert rotor_positions.keys() == expected_positions.keys()
    for name, expected in expected_positions.items():
        assert rotor_positions[name] == pytest.approx(expected, abs=1e-7)


def test_quadrotor_scene_validation_rejects_unknown_actuator() -> None:
    scene = _iris_scene()
    propulsion = deepcopy(scene.actors[0].properties["propulsion"])
    propulsion["rotors"][0]["actuator_id"] = "missing_rotor_actuator"
    scene.actors[0].properties["propulsion"] = propulsion

    with pytest.raises(ProjectValidationError, match="unknown actuator"):
        validate_scene(scene)


def test_controller_action_accepts_direct_rotor_controls() -> None:
    action = ControllerAction(
        actuator_controls={actuator_id: 660.0 for actuator_id in IRIS_ACTUATORS}
    )

    assert action.position_targets == {}
    assert tuple(action.actuator_controls) == IRIS_ACTUATORS
    with pytest.raises(TypeError):
        action.actuator_controls[IRIS_ACTUATORS[0]] = 0.0  # type: ignore[index]


def test_mujoco_quadrotor_controls_generate_lift(tmp_path) -> None:
    pytest.importorskip("mujoco")
    session = MuJoCoSimulationSession(
        _iris_scene(),
        tmp_path / "iris" / "scene.xml",
        asset_root=Path.cwd(),
    )
    initial_height = session.state().actors[0].position[2]

    commanded = session.set_actuator_controls(
        {actuator_id: 800.0 for actuator_id in IRIS_ACTUATORS}
    )
    stepped = session.step(steps=100)

    assert [item.ctrl for item in commanded.actuators] == pytest.approx([800.0] * 4)
    assert stepped.actors[0].position[2] > initial_height + 0.04
    observation = session._controller_observation().bodies["actor_iris"]
    assert observation.position[2] == pytest.approx(stepped.actors[0].position[2])
    assert sum(value * value for value in observation.linear_velocity) > 0.0
    model = session._quadrotor_models[0]
    body_id = session._link_ids[model.body_link_id]
    rotor_body_ids = [session._link_ids[rotor.link_id] for rotor in model.rotors]
    body_force = sum(float(value) ** 2 for value in session.data.xfrc_applied[body_id, :3]) ** 0.5
    assert body_force == pytest.approx(4 * 8.54858e-6 * 800.0**2)
    assert all(
        session.data.xfrc_applied[rotor_body_id].tolist() == [0.0] * 6
        for rotor_body_id in rotor_body_ids
    )


def test_loadable_iris_hover_controller_commands_all_rotors(tmp_path) -> None:
    pytest.importorskip("mujoco")
    loaded = ProjectControllerLoader(Path.cwd()).load(Path("examples/controllers/iris_hover.py"))
    session = MuJoCoSimulationSession(
        _iris_scene(),
        tmp_path / "controller" / "iris.xml",
        asset_root=Path.cwd(),
    )

    session.attach_controller(loaded.controller, name=loaded.name)
    state = session.step()

    assert state.controller.mode == "python"
    assert state.controller.status == "active"
    assert [item.ctrl for item in state.actuators] == pytest.approx(IRIS_HOVER_TRIM)


def test_iris_takeoff_controller_climbs_then_hovers_without_instability(
    tmp_path,
) -> None:
    pytest.importorskip("mujoco")
    loaded = ProjectControllerLoader(Path.cwd()).load(Path("examples/controllers/iris_hover.py"))
    session = MuJoCoSimulationSession(
        _iris_scene(),
        tmp_path / "hover" / "iris.xml",
        asset_root=Path.cwd(),
    )
    initial_position = session.state().actors[0].position

    session.attach_controller(loaded.controller, name=loaded.name)
    takeoff_state = session.step(steps=500)
    state = session.step(steps=2500)
    observation = session._controller_observation().bodies["actor_iris"]

    assert takeoff_state.actors[0].position[2] > initial_position[2] + 0.05
    assert state.time == pytest.approx(6.0)
    assert state.actors[0].position[:2] == pytest.approx(initial_position[:2], abs=1e-4)
    assert state.actors[0].position[2] == pytest.approx(initial_position[2] + 1.0, abs=1e-3)
    assert observation.linear_velocity == pytest.approx([0.0, 0.0, 0.0], abs=1e-3)
    assert observation.angular_velocity == pytest.approx([0.0, 0.0, 0.0], abs=1e-4)
    assert max(abs(joint.qvel) for joint in state.joints) < 1e-3


def test_quadrotor_algorithm_adapter_maps_hover_action_and_observes_pose(tmp_path) -> None:
    pytest.importorskip("mujoco")
    session = MujocoBackend().create_session(
        SceneBundle.from_scene(
            _iris_scene(),
            asset_root=Path.cwd(),
            export_path=tmp_path / "algorithm" / "iris.xml",
        )
    )
    initial = session.reset()
    adapter = QuadrotorAdapter(IRIS_ACTUATORS, body_id="actor_iris").bind(session.model_description)

    command = adapter.command([0.2, 0.2, 0.2, 0.2], initial)
    stepped = session.step(command, physics_steps=10)

    assert command.values == pytest.approx((660.0, 660.0, 660.0, 660.0))
    assert adapter.observation(stepped).shape == (13,)
    assert adapter.observation(stepped)[:3] == pytest.approx(stepped.body_positions[0])
    assert adapter.observation(stepped)[7:10] == pytest.approx(stepped.body_linear_velocities[0])
    session.close()
